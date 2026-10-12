import logging
import threading
from datetime import datetime, timezone
from typing import Optional
from django.db import connection
from django.core.management import call_command
from jobs.models import DiscoveryRunModel

logger = logging.getLogger(__name__)


def _run_in_background(target_func, *args, **kwargs):
    """
    Executes a function in a background daemon thread with safe
    Django database connection closing.
    """
    def wrapper():
        try:
            target_func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Unhandled background task error: {e}")
        finally:
            connection.close()

    thread = threading.Thread(target=wrapper, daemon=True)
    thread.start()
    return thread


def async_discover_jobs(is_live: bool = True, cap: int = 100, run_id: Optional[str] = None):
    """
    Asynchronously executes discover_jobs in a background thread.
    """
    def _execute():
        logger.info(f"Starting background job discovery (live={is_live}, cap={cap}, run_id={run_id})")
        run_record = None
        if run_id:
            run_record = DiscoveryRunModel.objects.filter(id=run_id).first()

        try:
            cmd_kwargs = {"cap": cap}
            if is_live:
                cmd_kwargs["live"] = True
            call_command("discover_jobs", **cmd_kwargs)
            logger.info("Background job discovery finished successfully.")
        except Exception as e:
            logger.exception(f"Background discovery task error: {e}")
            if run_record:
                run_record.status = "FAILED"
                run_record.errors = [str(e)]
                run_record.completed_at = datetime.now(timezone.utc)
                run_record.save(update_fields=["status", "errors", "completed_at"])

    return _run_in_background(_execute)


def async_inspect_and_discover(
    action: str = "catalog",
    limit: Optional[int] = None,
    url: str = "",
    name: str = "",
    then_discover: bool = True,
    run_id: Optional[str] = None,
):
    """
    Asynchronously executes career page inspection and optional chained discovery.
    """
    def _execute():
        logger.info(f"Starting background inspection (action={action}, limit={limit}, then_discover={then_discover})")
        run_record = None
        if run_id:
            run_record = DiscoveryRunModel.objects.filter(id=run_id).first()

        try:
            if action == "catalog":
                cmd_kwargs = {"catalog": True, "register": True, "concurrency": 5}
                if limit:
                    cmd_kwargs["limit"] = limit
                call_command("inspect_career_page", **cmd_kwargs)

            elif action == "single" and url:
                cmd_kwargs = {"url": url, "register": True}
                if name:
                    cmd_kwargs["name"] = name
                call_command("inspect_career_page", **cmd_kwargs)

            if then_discover:
                call_command("discover_jobs", live=True, cap=100)

            logger.info("Background inspection & cascaded discovery completed.")
        except Exception as e:
            logger.exception(f"Background inspection task error: {e}")
            if run_record:
                run_record.status = "FAILED"
                run_record.errors = [str(e)]
                run_record.completed_at = datetime.now(timezone.utc)
                run_record.save(update_fields=["status", "errors", "completed_at"])

    return _run_in_background(_execute)
