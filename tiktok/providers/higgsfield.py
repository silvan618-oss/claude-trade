"""Higgsfield ueber die HTTP-API.

Die konkreten Endpunkte, Feldnamen und Statuswerte stehen in
`higgsfield.schema.json` — so laesst sich eine geaenderte API-Signatur
anpassen, ohne Code zu editieren.

Ablauf pro Clip: Job anlegen -> pollen, bis fertig -> Video herunterladen.
Es laeuft immer nur ein Job gleichzeitig, weil die Plaene genau das hergeben.
"""

import json
import os
import time
import urllib.error
import urllib.request

from tiktok.config import Config
from tiktok.providers.base import ClipResult, GenerationFailed, download


def dig(data, path: str):
    """Holt einen verschachtelten Wert: 'results.0.url' -> data['results'][0]['url']."""
    current = data
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def fill(template, values: dict):
    """Ersetzt {platzhalter} rekursiv in Strings, Listen und Dicts."""
    if isinstance(template, str):
        # Steht der Platzhalter allein, bleibt der Typ erhalten (z. B. int).
        stripped = template.strip()
        if stripped.startswith("{") and stripped.endswith("}") and stripped[1:-1] in values:
            return values[stripped[1:-1]]
        for key, value in values.items():
            template = template.replace("{" + key + "}", str(value))
        return template
    if isinstance(template, dict):
        return {k: fill(v, values) for k, v in template.items() if not k.startswith("_")}
    if isinstance(template, list):
        return [fill(v, values) for v in template]
    return template


class HiggsfieldProvider:
    name = "higgsfield"
    supports_extend = True

    def __init__(self, config: Config):
        self.config = config
        if not config.higgsfield_api_key:
            raise GenerationFailed("HIGGSFIELD_API_KEY fehlt.")
        with open(config.higgsfield_schema, encoding="utf-8") as fh:
            self.schema = json.load(fh)

    # ---------- oeffentlich ----------

    def generate(self, prompt: str, seconds: int, aspect_ratio: str, out_path: str) -> ClipResult:
        return self._run("generate", prompt, seconds, aspect_ratio, out_path, source_id="")

    def extend(self, prompt: str, seconds: int, source: ClipResult, out_path: str) -> ClipResult:
        anchor = source.video_id or source.job_id
        if not anchor:
            raise GenerationFailed(
                "Kein Anker fuer extend — der vorherige Clip hat weder video_id noch job_id."
            )
        return self._run("extend", prompt, seconds, aspect_ratio="", out_path=out_path, source_id=anchor)

    # ---------- intern ----------

    def _run(self, op: str, prompt: str, seconds: int, aspect_ratio: str, out_path: str, source_id: str) -> ClipResult:
        spec = self.schema[op]
        values = {
            "model": self.config.video_model,
            "prompt": prompt,
            "seconds": seconds,
            "aspect_ratio": aspect_ratio or "9:16",
            "source_id": source_id,
        }
        response = self._request(
            spec.get("method", "POST"),
            fill(spec["path"], values),
            fill(spec.get("body", {}), values),
        )
        job_id = dig(response, spec.get("job_id_field", "id"))
        if not job_id:
            raise GenerationFailed(f"Keine Job-ID in der Antwort: {str(response)[:300]}")

        url, video_id = self._wait(str(job_id))
        index = int(os.path.splitext(os.path.basename(out_path))[0].split("_")[-1] or 0)
        download(url, out_path)
        return ClipResult(
            index=index,
            path=out_path,
            prompt=prompt,
            job_id=str(job_id),
            video_id=str(video_id or job_id),
            url=url,
            seconds=float(seconds),
        )

    def _wait(self, job_id: str) -> tuple[str, str]:
        spec = self.schema["status"]
        deadline = time.monotonic() + self.config.generation_timeout_seconds
        done = {v.lower() for v in spec.get("done_values", ["completed"])}
        failed = {v.lower() for v in spec.get("failed_values", ["failed"])}

        while time.monotonic() < deadline:
            data = self._request(
                spec.get("method", "GET"), fill(spec["path"], {"job_id": job_id}), None
            )
            status = str(dig(data, spec.get("status_field", "status")) or "").lower()
            if status in failed:
                raise GenerationFailed(
                    f"Job {job_id} fehlgeschlagen: {dig(data, spec.get('error_field', 'error'))}"
                )
            if status in done:
                url = dig(data, spec.get("video_url_field", "results.0.url"))
                if not url:
                    raise GenerationFailed(f"Job {job_id} fertig, aber ohne Video-URL.")
                return str(url), str(dig(data, spec.get("video_id_field", "")) or "")
            time.sleep(self.config.poll_interval_seconds)

        raise GenerationFailed(
            f"Job {job_id} nicht fertig nach {self.config.generation_timeout_seconds}s."
        )

    def _request(self, method: str, path: str, body: dict | None) -> dict:
        url = self.config.higgsfield_base_url.rstrip("/") + path
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header(
            self.schema.get("auth_header", "Authorization"),
            self.schema.get("auth_prefix", "Bearer ") + self.config.higgsfield_api_key,
        )
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            raise GenerationFailed(f"HTTP {exc.code} bei {method} {path}: {detail}") from exc
        return json.loads(raw) if raw.strip() else {}
