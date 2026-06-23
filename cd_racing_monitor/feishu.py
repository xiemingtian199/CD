from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError
from urllib import parse, request

from .config import FeishuConfig


FIELD_INPUT_MARKER = "🟩"
FIELD_IMPORTANT_MARKER = "🔴"


def normalize_field_label(name: str) -> str:
    label = str(name).strip()
    while label.startswith((FIELD_INPUT_MARKER, FIELD_IMPORTANT_MARKER)):
        label = label[1:].strip()
    return label


class FeishuClient:
    def __init__(self, config: FeishuConfig) -> None:
        self.config = config
        self._tenant_access_token: str | None = None
        self._bitable_app_token_value: str | None = None

    def list_records(self, table_id: str, page_size: int = 500) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = ""
        while True:
            query = {"page_size": str(page_size)}
            if page_token:
                query["page_token"] = page_token
            path = (
                f"/bitable/v1/apps/{self._bitable_app_token()}/tables/{table_id}/records"
                f"?{parse.urlencode(query)}"
            )
            payload = self._request("GET", path)
            data = payload.get("data", {})
            records.extend(data.get("items") or [])
            if not data.get("has_more"):
                break
            page_token = data.get("page_token", "")
            if not page_token:
                break
        for record in records:
            fields = record.get("fields")
            if isinstance(fields, dict):
                self._add_normalized_field_aliases(fields)
        return records

    def update_record(self, table_id: str, record_id: str, fields: dict[str, Any]) -> None:
        path = f"/bitable/v1/apps/{self._bitable_app_token()}/tables/{table_id}/records/{record_id}"
        self._request("PUT", path, {"fields": self._resolve_field_names(table_id, fields)})

    def update_records_batch(self, table_id: str, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        path = f"/bitable/v1/apps/{self._bitable_app_token()}/tables/{table_id}/records/batch_update"
        normalized_records = []
        for record in records:
            normalized = dict(record)
            fields = normalized.get("fields")
            if isinstance(fields, dict):
                normalized["fields"] = self._resolve_field_names(table_id, fields)
            normalized_records.append(normalized)
        payload = self._request("POST", path, {"records": normalized_records})
        updated = payload.get("data", {}).get("records", [])
        return len(updated) if updated else len(records)

    def list_tables(self) -> list[dict[str, Any]]:
        path = f"/bitable/v1/apps/{self._bitable_app_token()}/tables"
        payload = self._request("GET", path)
        return payload.get("data", {}).get("items", [])

    def create_table(self, name: str, default_field_name: str) -> str:
        path = f"/bitable/v1/apps/{self._bitable_app_token()}/tables"
        payload = self._request(
            "POST",
            path,
            {
                "table": {
                    "name": name,
                    "default_view_name": "默认视图",
                    "fields": [{"field_name": default_field_name, "type": 1}],
                }
            },
        )
        table = payload.get("data", {}).get("table", {})
        table_id = table.get("table_id") or table.get("id") or payload.get("data", {}).get("table_id")
        if not table_id:
            raise RuntimeError(f"Feishu created table {name}, but no table_id was returned")
        return table_id

    def list_fields(self, table_id: str) -> list[dict[str, Any]]:
        path = f"/bitable/v1/apps/{self._bitable_app_token()}/tables/{table_id}/fields"
        payload = self._request("GET", path)
        return payload.get("data", {}).get("items", [])

    def create_field(self, table_id: str, field_name: str, field_type: int) -> None:
        path = f"/bitable/v1/apps/{self._bitable_app_token()}/tables/{table_id}/fields"
        self._request("POST", path, {"field_name": field_name, "type": field_type})

    def update_field(self, table_id: str, field_id: str, field_name: str, field_type: int) -> None:
        path = f"/bitable/v1/apps/{self._bitable_app_token()}/tables/{table_id}/fields/{field_id}"
        self._request("PUT", path, {"field_name": field_name, "type": field_type})

    def delete_field(self, table_id: str, field_id: str) -> None:
        path = f"/bitable/v1/apps/{self._bitable_app_token()}/tables/{table_id}/fields/{field_id}"
        self._request("DELETE", path)

    def create_record(self, table_id: str, fields: dict[str, Any]) -> str:
        path = f"/bitable/v1/apps/{self._bitable_app_token()}/tables/{table_id}/records"
        payload = self._request("POST", path, {"fields": self._resolve_field_names(table_id, fields)})
        record = payload.get("data", {}).get("record", {})
        return str(record.get("record_id", ""))

    def delete_record(self, table_id: str, record_id: str) -> None:
        path = f"/bitable/v1/apps/{self._bitable_app_token()}/tables/{table_id}/records/{record_id}"
        self._request("DELETE", path)

    def create_records_batch(self, table_id: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        path = f"/bitable/v1/apps/{self._bitable_app_token()}/tables/{table_id}/records/batch_create"
        payload = self._request(
            "POST",
            path,
            {"records": [{"fields": self._resolve_field_names(table_id, row)} for row in rows]},
        )
        records = payload.get("data", {}).get("records", [])
        return len(records) if records else len(rows)

    def _resolve_field_names(self, table_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        if not fields:
            return fields
        actual_by_name: dict[str, str] = {}
        actual_by_normalized: dict[str, str] = {}
        for field in self.list_fields(table_id):
            actual = str(field.get("field_name") or field.get("name") or "")
            if not actual:
                continue
            actual_by_name[actual] = actual
            actual_by_normalized.setdefault(normalize_field_label(actual), actual)

        resolved: dict[str, Any] = {}
        for key, value in fields.items():
            key_text = str(key)
            resolved_key = actual_by_name.get(key_text) or actual_by_normalized.get(
                normalize_field_label(key_text),
                key_text,
            )
            resolved[resolved_key] = value
        return resolved

    @staticmethod
    def _add_normalized_field_aliases(fields: dict[str, Any]) -> None:
        for key, value in list(fields.items()):
            normalized = normalize_field_label(str(key))
            if normalized and normalized != key and normalized not in fields:
                fields[normalized] = value

    def _bitable_app_token(self) -> str:
        if self._bitable_app_token_value:
            return self._bitable_app_token_value
        wiki_path = f"/wiki/v2/spaces/get_node?{parse.urlencode({'token': self.config.app_token})}"
        try:
            payload = self._request("GET", wiki_path)
            node = payload.get("data", {}).get("node", {})
            obj_token = node.get("obj_token")
            obj_type = node.get("obj_type", "")
            if obj_token and obj_type in ("bitable", "sheet"):
                self._bitable_app_token_value = str(obj_token)
                return self._bitable_app_token_value
        except Exception:
            pass
        self._bitable_app_token_value = self.config.app_token
        return self._bitable_app_token_value

    def _tenant_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token
        payload = self._request(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            {"app_id": self.config.app_id, "app_secret": self.config.app_secret},
            auth=False,
        )
        token = payload.get("tenant_access_token")
        if not token:
            raise RuntimeError("Feishu did not return tenant_access_token")
        self._tenant_access_token = token
        return token

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if auth:
            headers["Authorization"] = f"Bearer {self._tenant_token()}"
        response_body = ""
        for attempt in range(3):
            req = request.Request(url, data=data, headers=headers, method=method)
            try:
                with request.urlopen(req, timeout=45) as response:
                    response_body = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Feishu request failed: {method} {path}: HTTP {exc.code} {error_body}") from exc
            except Exception as exc:
                if attempt == 2:
                    raise RuntimeError(f"Feishu request failed: {method} {path}: {exc}") from exc
                time.sleep(1.5 * (attempt + 1))
        payload = json.loads(response_body) if response_body else {}
        code = payload.get("code", 0)
        if code != 0:
            message = payload.get("msg", "unknown error")
            raise RuntimeError(f"Feishu API error {code}: {message}")
        return payload
