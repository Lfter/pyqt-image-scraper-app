import json


class NetworkImageCollector:
    def __init__(self, extractor, resolver=None):
        self.extractor = extractor
        self.resolver = resolver or extractor.resolver
        self.reset()

    def reset(self):
        self.primary_network_candidates = []
        self.network_candidates = []
        self.primary_network_image_urls = []
        self.network_image_urls = []

    def capture_response(self, response):
        payload = self.parse_response_payload(response)
        if payload is None:
            return

        response_url = getattr(response, "url", "") or ""
        extracted_candidates = self.extractor.extract_payload_candidates(
            payload,
            response_url,
            source="payload",
        )
        if not extracted_candidates:
            return

        if self.is_primary_image_payload(response_url, payload):
            self.primary_network_candidates = self.resolver.merge_candidates(
                extracted_candidates,
                self.primary_network_candidates,
            )
            self.network_candidates = self.resolver.merge_candidates(
                self.primary_network_candidates,
                self.network_candidates,
            )
        else:
            self.network_candidates = self.resolver.merge_candidates(
                extracted_candidates,
                self.network_candidates,
            )

        self.sync_urls()

    def sync_urls(self):
        self.primary_network_image_urls = [candidate.url for candidate in self.primary_network_candidates]
        self.network_image_urls = [candidate.url for candidate in self.network_candidates]

    def parse_response_payload(self, response):
        content_type = (self.get_response_content_type(response) or "").lower()
        resource_type = self.get_response_resource_type(response)

        if content_type and "json" not in content_type and resource_type not in {"xhr", "fetch"}:
            return None

        text = self.get_response_text(response)
        if not text:
            return None

        if "json" not in content_type and resource_type not in {"xhr", "fetch"}:
            stripped = text.lstrip()
            if not stripped.startswith(("{", "[")):
                return None

        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return None

    def get_response_content_type(self, response):
        header_value = getattr(response, "header_value", None)
        if callable(header_value):
            try:
                content_type = header_value("content-type")
                if content_type:
                    return content_type
            except Exception:
                pass

        headers = getattr(response, "headers", None)
        if callable(headers):
            try:
                headers = headers()
            except Exception:
                headers = None

        if isinstance(headers, dict):
            for key, value in headers.items():
                if str(key).lower() == "content-type":
                    return value

        return ""

    def get_response_resource_type(self, response):
        request = getattr(response, "request", None)
        if request is None:
            return ""

        resource_type = getattr(request, "resource_type", "")
        if callable(resource_type):
            try:
                return resource_type()
            except Exception:
                return ""
        return resource_type or ""

    def get_response_text(self, response):
        text_method = getattr(response, "text", None)
        if callable(text_method):
            try:
                return text_method()
            except Exception:
                return None
        return None

    def is_primary_image_payload(self, response_url: str, payload) -> bool:
        lowered_url = response_url.lower()
        if any(marker in lowered_url for marker in ("/pic/", "/photo/", "/image/", "/gallery/", "/album/")):
            return True
        return self.payload_contains_priority_fields(payload)

    def payload_contains_priority_fields(self, payload) -> bool:
        def walk(node, path_segments=()):
            if isinstance(node, dict):
                for key, value in node.items():
                    if walk(value, path_segments + (str(key).lower(),)):
                        return True
                return False

            if isinstance(node, list):
                return any(walk(item, path_segments) for item in node)

            if not isinstance(node, str):
                return False

            path_text = " ".join(path_segments)
            if not self.extractor.looks_like_payload_image_value(node):
                return False

            has_priority_marker = any(
                marker in path_text for marker in ("origin", "original", "master", "raw", "download")
            )
            has_image_marker = any(
                marker in path_text for marker in ("img", "image", "pic", "photo", "cover", "poster")
            )
            return has_priority_marker and has_image_marker

        return walk(payload)
