import asyncio
import logging
import re
import time
from asyncio import Event
from typing import Any, Dict, List, Set

from fastapi import Depends
from playwright.async_api import Page as AsyncPage

from config import DEFAULT_FALLBACK_MODEL_ID

from ..dependencies import (
    ensure_request_lock,
    get_excluded_model_ids,
    get_logger,
    get_model_list_fetch_event,
    get_page_instance,
    get_parsed_model_list,
)

# LOCAL PATCH: ids that are not plain chat models (mirrors the exclusion
# intent of AIStudio2API's own model list, which the magpie-gemini-web
# plugin is written against).
_NON_CHAT_ID_RE = re.compile(
    r"(image|nano-banana|tts|audio|live|transcribe|robotics|research|video|music|canvas)",
    re.IGNORECASE,
)


def _enrich_model_entry(model: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a parsed model entry with AIStudio2API-style fields.

    The magpie-gemini-web plugin's ai-studio provider only accepts models
    whose list entries carry supported_generation_methods and a
    capabilities object with chat_model=true (plus token limits under
    input_token_limit/output_token_limit). Our parser keeps the upstream
    fields under different names, so translate them here at the API edge
    and leave the internal parsed list untouched.
    """
    entry = dict(model)
    model_id = entry.get("id") or ""

    if "supported_generation_methods" not in entry:
        entry["supported_generation_methods"] = [
            "generateContent",
            "streamGenerateContent",
        ]

    is_chat_model = (
        model_id.startswith("gemini-")
        and not _NON_CHAT_ID_RE.search(model_id)
        and not model_id.lower().endswith("-build")
    )
    if is_chat_model:
        caps = dict(entry.get("capabilities") or {})
        caps.setdefault("chat_model", True)
        caps.setdefault("function_declarations", True)
        caps.setdefault("thinking", True)
        caps.setdefault("thinking_level", True)
        caps.setdefault("media_resolution", True)
        entry["capabilities"] = caps

    if "output_token_limit" not in entry and entry.get(
        "supported_max_output_tokens"
    ):
        entry["output_token_limit"] = entry["supported_max_output_tokens"]
    if "name" not in entry and entry.get("display_name"):
        entry["name"] = entry["display_name"]
    return entry


async def list_models(
    logger: logging.Logger = Depends(get_logger),
    model_list_fetch_event: Event = Depends(get_model_list_fetch_event),
    page_instance: AsyncPage = Depends(get_page_instance),
    parsed_model_list: List[Dict[str, Any]] = Depends(get_parsed_model_list),
    excluded_model_ids: Set[str] = Depends(get_excluded_model_ids),
    _lock: None = Depends(ensure_request_lock),
):
    logger.debug("[API] Received /v1/models request.")

    if (
        not model_list_fetch_event.is_set()
        and page_instance
        and not page_instance.is_closed()
    ):
        logger.info(
            "/v1/models: Model list event not set, attempting to refresh page..."
        )
        try:
            await page_instance.reload(wait_until="domcontentloaded", timeout=20000)
            await asyncio.wait_for(model_list_fetch_event.wait(), timeout=10.0)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"/v1/models: Error refreshing or waiting for model list: {e}")
        finally:
            if not model_list_fetch_event.is_set():
                model_list_fetch_event.set()

    if parsed_model_list:
        final_model_list = [
            _enrich_model_entry(m)
            for m in parsed_model_list
            if isinstance(m, dict) and m.get("id") not in excluded_model_ids
        ]
        return {"object": "list", "data": final_model_list}
    else:
        logger.warning("Model list is empty, returning default fallback model.")
        return {
            "object": "list",
            "data": [
                {
                    "id": DEFAULT_FALLBACK_MODEL_ID,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "camoufox-proxy-fallback",
                }
            ],
        }
