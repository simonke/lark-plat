"""Script service: versioned scripts, rollback, parameter validation, reference checks."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.db.models import Script, ScriptVersion
from app.repositories import ScriptRepository, ScriptVersionRepository
from app import schemas


def _version_no(db: Session, script_id: int) -> int:
    from sqlalchemy import func

    cur = db.query(func.max(ScriptVersion.version)).filter(ScriptVersion.script_id == script_id).scalar()
    return int(cur or 0) + 1


def list_scripts(db: Session, name: str | None, type_: str | None, page: int, size: int) -> dict:
    rows, total = ScriptRepository(db).search(name, type_, page, size)
    return {
        "list": [schemas.ScriptOut.model_validate(s).model_dump() for s in rows],
        "total": total, "page": page, "size": size,
    }


def get_script(db: Session, script_id: int, version: int | None = None) -> dict:
    repo = ScriptRepository(db)
    script = repo.get(script_id)
    if script is None:
        raise NotFoundError("script not found")
    v = version or script.current_version
    sv = ScriptVersionRepository(db).by_script_version(script_id, v)
    if sv is None:
        raise NotFoundError("script version not found")
    data = schemas.ScriptOut.model_validate(script).model_dump()
    data["content"] = sv.content
    data["params_def"] = sv.params_def or script.params_def
    data["requested_version"] = v
    return data


def create_script(db: Session, user, data: schemas.ScriptCreate) -> int:
    if data.type not in ("shell", "powershell", "python"):
        raise BadRequestError("invalid script type")
    script = Script(
        name=data.name, type=data.type, current_version=1,
        params_def=data.params_def, remark=data.remark, created_by=user.id,
    )
    ScriptRepository(db).add(script)
    db.flush()
    ScriptVersionRepository(db).add(ScriptVersion(
        script_id=script.id, version=1, content=data.content,
        params_def=data.params_def, change_log="initial", created_by=user.id,
    ))
    db.commit()
    return script.id


def update_script(db: Session, user, script_id: int, data: schemas.ScriptUpdate) -> dict:
    repo = ScriptRepository(db)
    script = repo.get(script_id)
    if script is None:
        raise NotFoundError("script not found")
    if not data.content:
        raise BadRequestError("content required for new version")
    new_version = _version_no(db, script_id)
    ScriptVersionRepository(db).add(ScriptVersion(
        script_id=script_id, version=new_version, content=data.content,
        params_def=data.params_def if data.params_def is not None else script.params_def,
        change_log=data.change_log or "", created_by=user.id,
    ))
    script.current_version = new_version
    if data.params_def is not None:
        script.params_def = data.params_def
    if data.remark is not None:
        script.remark = data.remark
    db.commit()
    return {"id": script_id, "current_version": new_version}


def delete_script(db: Session, script_id: int) -> None:
    repo = ScriptRepository(db)
    script = repo.get(script_id)
    if script is None:
        raise NotFoundError("script not found")
    if repo.referenced_count(script_id) > 0:
        raise ConflictError("script referenced by tasks or schedules")
    db.delete(script)
    db.commit()


def list_versions(db: Session, script_id: int) -> dict:
    if ScriptRepository(db).get(script_id) is None:
        raise NotFoundError("script not found")
    versions = ScriptVersionRepository(db).list_versions(script_id)
    return {
        "list": [
            {"id": v.id, "script_id": v.script_id, "version": v.version, "content": v.content,
             "params_def": v.params_def, "change_log": v.change_log, "created_by": v.created_by,
             "created_at": v.created_at.isoformat() if v.created_at else None}
            for v in versions
        ],
        "total": len(versions),
    }


def get_version(db: Session, script_id: int, version: int) -> dict:
    sv = ScriptVersionRepository(db).by_script_version(script_id, version)
    if sv is None:
        raise NotFoundError("script version not found")
    return {
        "id": sv.id, "script_id": sv.script_id, "version": sv.version, "content": sv.content,
        "params_def": sv.params_def, "change_log": sv.change_log,
        "created_at": sv.created_at.isoformat() if sv.created_at else None,
    }


def rollback(db: Session, user, script_id: int, version: int) -> dict:
    repo = ScriptRepository(db)
    script = repo.get(script_id)
    if script is None:
        raise NotFoundError("script not found")
    sv = ScriptVersionRepository(db).by_script_version(script_id, version)
    if sv is None:
        raise NotFoundError("script version not found")
    script.current_version = version
    script.params_def = sv.params_def if sv.params_def is not None else script.params_def
    db.commit()
    return {"id": script_id, "current_version": version}


def test_params(db: Session, script_id: int, params: dict | None) -> dict:
    script = ScriptRepository(db).get(script_id)
    if script is None:
        raise NotFoundError("script not found")
    sv = ScriptVersionRepository(db).by_script_version(script_id, script.current_version)
    pdef = (sv.params_def if sv else None) or script.params_def or {}
    errors = []
    for name, spec in (pdef or {}).items():
        required = spec.get("required", False) if isinstance(spec, dict) else False
        if required and (not params or name not in params):
            errors.append(f"missing required param: {name}")
    return {"ok": not errors, "errors": errors}
