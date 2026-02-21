"""Ingestion endpoints with proper error handling (SEC-014).

SEC-014: Replaced silent exception handling with specific exception handling and logging.
SD-024: Cache invalidation added after ingestion completes.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.postgres import get_db
from db.redis import get_redis
from models.schemas import IngestionResult, IngestionStatus
from routers.auth import get_current_user_id
from services.extractor import DecisionExtractor
from services.file_watcher import get_file_watcher
from services.parser import ClaudeLogParser
from utils.cache import invalidate_user_caches
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Track ingestion state
ingestion_state = {
    "is_watching": False,
    "last_run": None,
    "files_processed": 0,
}

# Import job state keys
IMPORT_JOB_KEY = "import:current_job"
IMPORT_CANCEL_KEY = "import:cancel"


class ProjectInfo(BaseModel):
    dir: str
    name: str
    files: int
    path: str


class ConversationPreview(BaseModel):
    file: str
    project: str
    messages: int
    preview: str


class PreviewResponse(BaseModel):
    total_conversations: int
    previews: list[ConversationPreview]
    project_filter: Optional[str]
    exclude_projects: list[str]


class FileInfo(BaseModel):
    """Information about a single JSONL file."""
    file_path: str
    project_name: str
    project_dir: str
    conversation_count: int
    size_bytes: int
    last_modified: str


class ImportSelectedRequest(BaseModel):
    """Request to import selected files to a target project."""
    file_paths: list[str]
    target_project: Optional[str] = None


class ImportProgress(BaseModel):
    """Current import job progress."""
    job_id: Optional[str] = None
    status: str  # idle, running, completed, cancelled, error
    total_files: int = 0
    processed_files: int = 0
    current_file: Optional[str] = None
    decisions_extracted: int = 0
    errors: list[str] = []
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@router.get("/projects", response_model=list[ProjectInfo])
async def list_available_projects():
    """List all Claude Code projects available for ingestion.

    Returns project directories with conversation file counts.
    Use this to see what projects are available before filtering.
    """
    settings = get_settings()
    parser = ClaudeLogParser(settings.claude_logs_path)
    return parser.get_available_projects()


@router.get("/files", response_model=list[FileInfo])
async def list_files(
    project: Optional[str] = Query(
        None, description="Only include this project (partial match)"
    ),
):
    """List all Claude Code log files with metadata for selective import.

    Returns file information including path, project, conversation count, size, and timestamp.
    Use this to build a file browser UI for selective import.
    """
    settings = get_settings()
    parser = ClaudeLogParser(settings.claude_logs_path)

    if not parser.logs_path.exists():
        return []

    files_info = []

    # Find all JSONL files
    for file_path in parser.logs_path.glob("**/*.jsonl"):
        # Skip subagent files
        if "subagents" in str(file_path):
            continue

        project_name = parser._extract_project_name(file_path)
        project_dir = file_path.parent.name

        # Apply project filter if provided
        if project and project.lower() not in project_dir.lower():
            continue

        # Get file stats
        stat = file_path.stat()

        # Count conversations in file
        conversations = parser._parse_jsonl_file(file_path)

        files_info.append(
            FileInfo(
                file_path=str(file_path),
                project_name=project_name,
                project_dir=project_dir,
                conversation_count=len(conversations),
                size_bytes=stat.st_size,
                last_modified=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            )
        )

    # Sort by last modified (newest first)
    files_info.sort(key=lambda x: x.last_modified, reverse=True)

    return files_info


@router.get("/preview", response_model=PreviewResponse)
async def preview_ingestion(
    project: Optional[str] = Query(
        None, description="Only include this project (partial match)"
    ),
    exclude: Optional[str] = Query(
        None, description="Comma-separated list of projects to exclude"
    ),
    limit: int = Query(10, ge=1, le=50, description="Max conversations to preview"),
):
    """Preview what would be imported without actually importing.

    Use this to verify your filters before running ingestion.
    """
    settings = get_settings()
    parser = ClaudeLogParser(settings.claude_logs_path)

    exclude_list = [e.strip() for e in exclude.split(",")] if exclude else []

    previews = await parser.preview_logs(
        project_filter=project,
        exclude_projects=exclude_list,
        max_conversations=limit,
    )

    return PreviewResponse(
        total_conversations=len(previews),
        previews=[ConversationPreview(**p) for p in previews],
        project_filter=project,
        exclude_projects=exclude_list,
    )


@router.get("/status", response_model=IngestionStatus)
async def get_ingestion_status():
    """Get the current ingestion status."""
    return IngestionStatus(
        is_watching=ingestion_state["is_watching"],
        last_run=ingestion_state["last_run"],
        files_processed=ingestion_state["files_processed"],
    )


async def get_import_progress() -> ImportProgress:
    """Get current import job progress from Redis."""
    redis = await get_redis()
    if not redis:
        return ImportProgress(status="idle")

    job_data = await redis.hgetall(IMPORT_JOB_KEY)
    if not job_data:
        return ImportProgress(status="idle")

    return ImportProgress(
        job_id=job_data.get("job_id"),
        status=job_data.get("status", "idle"),
        total_files=int(job_data.get("total_files", 0)),
        processed_files=int(job_data.get("processed_files", 0)),
        current_file=job_data.get("current_file"),
        decisions_extracted=int(job_data.get("decisions_extracted", 0)),
        errors=job_data.get("errors", "").split("|") if job_data.get("errors") else [],
        started_at=job_data.get("started_at"),
        completed_at=job_data.get("completed_at"),
    )


async def update_import_progress(
    job_id: str,
    status: str,
    total_files: int = 0,
    processed_files: int = 0,
    current_file: Optional[str] = None,
    decisions_extracted: int = 0,
    errors: Optional[list[str]] = None,
    completed_at: Optional[str] = None,
) -> None:
    """Update import job progress in Redis."""
    redis = await get_redis()
    if not redis:
        return

    data = {
        "job_id": job_id,
        "status": status,
        "total_files": str(total_files),
        "processed_files": str(processed_files),
        "current_file": current_file or "",
        "decisions_extracted": str(decisions_extracted),
        "errors": "|".join(errors) if errors else "",
    }
    if completed_at:
        data["completed_at"] = completed_at

    await redis.hset(IMPORT_JOB_KEY, mapping=data)
    # Expire job data after 1 hour
    await redis.expire(IMPORT_JOB_KEY, 3600)


async def is_import_cancelled() -> bool:
    """Check if current import should be cancelled."""
    redis = await get_redis()
    if not redis:
        return False
    return await redis.exists(IMPORT_CANCEL_KEY) > 0


async def clear_import_state() -> None:
    """Clear import job state."""
    redis = await get_redis()
    if redis:
        await redis.delete(IMPORT_JOB_KEY, IMPORT_CANCEL_KEY)


@router.get("/import/progress", response_model=ImportProgress)
async def get_current_import_progress():
    """Get the current import job progress.

    Poll this endpoint while an import is running to track progress.
    """
    return await get_import_progress()


@router.post("/import/cancel")
async def cancel_import():
    """Cancel the currently running import job.

    Sets a cancellation flag that the import process checks periodically.
    The import will stop after completing the current file.
    """
    progress = await get_import_progress()
    if progress.status != "running":
        raise HTTPException(status_code=400, detail="No import is currently running")

    redis = await get_redis()
    if redis:
        await redis.set(IMPORT_CANCEL_KEY, "1", ex=300)  # 5 min expiry

    return {"status": "cancellation_requested", "job_id": progress.job_id}


async def run_import_job(
    job_id: str,
    file_paths: list[str],
    target_project: Optional[str] = None,
    user_id: str = "anonymous",
) -> None:
    """Background task to run the import with progress tracking."""
    from pathlib import Path

    settings = get_settings()
    parser = ClaudeLogParser(settings.claude_logs_path)
    extractor = DecisionExtractor()

    total_files = len(file_paths)
    processed_files = 0
    decisions_extracted = 0
    errors: list[str] = []

    try:
        # Update initial state
        await update_import_progress(
            job_id=job_id,
            status="running",
            total_files=total_files,
            processed_files=0,
            decisions_extracted=0,
        )

        for file_path_str in file_paths:
            # Check for cancellation
            if await is_import_cancelled():
                logger.info(f"Import job {job_id} cancelled by user")
                await update_import_progress(
                    job_id=job_id,
                    status="cancelled",
                    total_files=total_files,
                    processed_files=processed_files,
                    decisions_extracted=decisions_extracted,
                    errors=errors,
                    completed_at=datetime.now(UTC).isoformat(),
                )
                return

            file_path = Path(file_path_str)

            # Update current file
            await update_import_progress(
                job_id=job_id,
                status="running",
                total_files=total_files,
                processed_files=processed_files,
                current_file=file_path.name,
                decisions_extracted=decisions_extracted,
                errors=errors,
            )

            try:
                conversations = parser._parse_jsonl_file(file_path)

                for conversation in conversations:
                    # Check for cancellation between conversations
                    if await is_import_cancelled():
                        break

                    try:
                        decisions = await extractor.extract_decisions(conversation)
                        decisions_extracted += len(decisions)

                        # Use target project or original project
                        project_name = target_project or conversation.project_name

                        for decision in decisions:
                            try:
                                await extractor.save_decision(
                                    decision,
                                    source="claude_logs",
                                    project_name=project_name,
                                )
                            except Exception as save_error:
                                logger.error(f"Failed to save decision: {save_error}")
                                errors.append(f"save:{file_path.name}")
                    except Exception as extract_error:
                        logger.error(f"Failed to extract from {file_path}: {extract_error}")
                        errors.append(f"extract:{file_path.name}")

                    # Update progress after each conversation
                    await update_import_progress(
                        job_id=job_id,
                        status="running",
                        total_files=total_files,
                        processed_files=processed_files,
                        current_file=file_path.name,
                        decisions_extracted=decisions_extracted,
                        errors=errors,
                    )

                processed_files += 1

            except Exception as file_error:
                logger.error(f"Error processing {file_path}: {file_error}")
                errors.append(f"file:{file_path.name}")
                processed_files += 1

        # Completed
        ingestion_state["files_processed"] += processed_files
        ingestion_state["last_run"] = datetime.now(UTC)

        final_status = "completed" if not errors else f"completed with {len(errors)} errors"
        await update_import_progress(
            job_id=job_id,
            status=final_status,
            total_files=total_files,
            processed_files=processed_files,
            current_file=None,
            decisions_extracted=decisions_extracted,
            errors=errors,
            completed_at=datetime.now(UTC).isoformat(),
        )

        # Invalidate caches for the authenticated user who triggered this import
        await invalidate_user_caches(user_id)
        logger.info(f"Import job {job_id} completed: {processed_files} files, {decisions_extracted} decisions")

    except Exception as e:
        logger.error(f"Import job {job_id} failed: {e}", exc_info=True)
        await update_import_progress(
            job_id=job_id,
            status=f"error: {type(e).__name__}",
            total_files=total_files,
            processed_files=processed_files,
            decisions_extracted=decisions_extracted,
            errors=errors + [str(e)],
            completed_at=datetime.now(UTC).isoformat(),
        )


@router.post("/trigger")
async def trigger_ingestion(
    background_tasks: BackgroundTasks,
    project: Optional[str] = Query(
        None, description="Only include this project (partial match)"
    ),
    exclude: Optional[str] = Query(
        None, description="Comma-separated list of projects to exclude"
    ),
    user_id: str = Depends(get_current_user_id),
):
    """Trigger ingestion of Claude Code logs with optional filtering.

    This starts a background import job. Use GET /import/progress to track progress.
    Use POST /import/cancel to stop an in-progress import.

    Examples:
    - /api/ingest/trigger?project=continuum - Only import from continuum project
    - /api/ingest/trigger?exclude=CS5330,CS6120 - Exclude coursework
    """
    # Check if import is already running
    progress = await get_import_progress()
    if progress.status == "running":
        raise HTTPException(
            status_code=409,
            detail="An import is already in progress. Cancel it first or wait for completion."
        )

    settings = get_settings()
    parser = ClaudeLogParser(settings.claude_logs_path)

    exclude_list = [e.strip() for e in exclude.split(",")] if exclude else []

    # Collect all file paths
    file_paths: list[str] = []
    try:
        async for file_path, _ in parser.parse_all_logs(
            project_filter=project,
            exclude_projects=exclude_list,
        ):
            file_paths.append(str(file_path))
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Claude logs path not found: {settings.claude_logs_path}",
        )

    if not file_paths:
        return {"status": "no_files", "job_id": None, "total_files": 0}

    # Clear any previous state
    await clear_import_state()

    # Start background job
    job_id = str(uuid.uuid4())

    # Initialize progress
    redis = await get_redis()
    if redis:
        await redis.hset(IMPORT_JOB_KEY, mapping={
            "job_id": job_id,
            "status": "starting",
            "total_files": str(len(file_paths)),
            "processed_files": "0",
            "current_file": "",
            "decisions_extracted": "0",
            "errors": "",
            "started_at": datetime.now(UTC).isoformat(),
        })
        await redis.expire(IMPORT_JOB_KEY, 3600)

    background_tasks.add_task(run_import_job, job_id, file_paths, None, user_id)

    return {
        "status": "started",
        "job_id": job_id,
        "total_files": len(file_paths),
    }


@router.post("/import-selected")
async def import_selected_files(
    request: ImportSelectedRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    """Import only selected files with optional target project assignment.

    This starts a background import job. Use GET /import/progress to track progress.
    Use POST /import/cancel to stop an in-progress import.

    Examples:
    - Import specific files to a project: {"file_paths": [...], "target_project": "continuum"}
    - Import files with original project names: {"file_paths": [...], "target_project": null}
    """
    from pathlib import Path

    # Check if import is already running
    progress = await get_import_progress()
    if progress.status == "running":
        raise HTTPException(
            status_code=409,
            detail="An import is already in progress. Cancel it first or wait for completion."
        )

    settings = get_settings()
    parser = ClaudeLogParser(settings.claude_logs_path)

    # Validate files
    valid_paths: list[str] = []
    errors: list[str] = []

    for file_path_str in request.file_paths:
        file_path = Path(file_path_str)

        if not file_path.exists():
            errors.append(f"not_found:{file_path_str}")
            continue

        # Security: Ensure file is within logs directory
        try:
            file_path.resolve().relative_to(parser.logs_path.resolve())
            valid_paths.append(file_path_str)
        except ValueError:
            logger.warning(f"Attempted to import file outside logs directory: {file_path}")
            errors.append(f"invalid_path:{file_path_str}")

    if not valid_paths:
        return {"status": "no_valid_files", "job_id": None, "total_files": 0, "errors": errors}

    # Clear any previous state
    await clear_import_state()

    # Start background job
    job_id = str(uuid.uuid4())

    # Initialize progress
    redis = await get_redis()
    if redis:
        await redis.hset(IMPORT_JOB_KEY, mapping={
            "job_id": job_id,
            "status": "starting",
            "total_files": str(len(valid_paths)),
            "processed_files": "0",
            "current_file": "",
            "decisions_extracted": "0",
            "errors": "|".join(errors) if errors else "",
            "started_at": datetime.now(UTC).isoformat(),
        })
        await redis.expire(IMPORT_JOB_KEY, 3600)

    background_tasks.add_task(run_import_job, job_id, valid_paths, request.target_project, user_id)

    return {
        "status": "started",
        "job_id": job_id,
        "total_files": len(valid_paths),
        "validation_errors": errors,
    }


async def process_changed_file(file_path: str) -> None:
    """Process a changed Claude log file.

    This is called by the file watcher when a file changes.

    SEC-014: Proper error handling with specific exceptions and logging.
    """
    logger.info(f"Processing changed file: {file_path}")

    try:
        parser = ClaudeLogParser("")
        conversations = await parser.parse_file(file_path)

        extractor = DecisionExtractor()
        decisions_extracted = 0

        for conversation in conversations:
            try:
                decisions = await extractor.extract_decisions(conversation)
                decisions_extracted += len(decisions)

                for decision in decisions:
                    try:
                        await extractor.save_decision(
                            decision,
                            source="claude_logs",
                            project_name=conversation.project_name
                        )
                    except Exception as save_error:
                        logger.error(
                            f"Failed to save decision from {file_path}: "
                            f"{type(save_error).__name__}: {save_error}",
                            exc_info=True,
                        )
            except Exception as extract_error:
                logger.error(
                    f"Failed to extract decisions from {file_path}: "
                    f"{type(extract_error).__name__}: {extract_error}",
                    exc_info=True,
                )

        ingestion_state["files_processed"] += 1
        ingestion_state["last_run"] = datetime.now(UTC)
        logger.info(f"Processed {decisions_extracted} decisions from {file_path}")

    except FileNotFoundError:
        logger.warning(f"File not found (may have been deleted): {file_path}")
    except PermissionError as e:
        logger.error(f"Permission denied reading file {file_path}: {e}")
    except Exception as e:
        logger.error(
            f"Error processing file {file_path}: {type(e).__name__}: {e}", exc_info=True
        )


@router.post("/watch/start")
async def start_watching(background_tasks: BackgroundTasks):
    """Start watching Claude Code logs for new conversations.

    Uses watchdog to monitor the logs directory for new or modified
    JSONL files. When changes are detected, decisions are automatically
    extracted and saved to the knowledge graph.
    """
    settings = get_settings()
    watcher = get_file_watcher()

    if watcher.is_running:
        return {"status": "already watching", "path": settings.claude_logs_path}

    success = watcher.start(
        logs_path=settings.claude_logs_path,
        on_change=lambda path: background_tasks.add_task(process_changed_file, path),
    )

    if success:
        ingestion_state["is_watching"] = True
        return {"status": "watching started", "path": settings.claude_logs_path}
    else:
        return {"status": "failed to start", "error": "Could not start file watcher"}


@router.post("/watch/stop")
async def stop_watching():
    """Stop watching Claude Code logs."""
    watcher = get_file_watcher()

    if not watcher.is_running:
        return {"status": "not watching"}

    watcher.stop()
    ingestion_state["is_watching"] = False
    return {"status": "watching stopped"}
