"""
title: OpenWebUI Skills Manager Tool
author: Fu-Jie
author_url: https://github.com/Fu-Jie/openwebui-extensions
funding_url: https://github.com/open-webui
version: 0.4.0
openwebui_id: b4bce8e4-08e7-4f90-bea7-dc31d463a0bb
requirements:
description: Standalone OpenWebUI tool for managing native Workspace Skills (list/show/create/update) for any model.
"""

import logging
import uuid
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from open_webui.models.skills import Skills, SkillForm, SkillMeta
except Exception:
    Skills = None
    SkillForm = None
    SkillMeta = None


def _get_user_id(__user__: Optional[dict]) -> str:
    """Extract user id from trusted server-side input."""
    if isinstance(__user__, (list, tuple)):
        user_data = __user__[0] if __user__ else {}
    elif isinstance(__user__, dict):
        user_data = __user__
    else:
        user_data = {}
    return str(user_data.get("id", "")).strip()


async def _emit_status(
    valves,
    emitter: Optional[Any],
    description: str,
    done: bool = False,
):
    """Emit status event to OpenWebUI status bar when enabled."""
    if valves.SHOW_STATUS and emitter:
        await emitter(
            {
                "type": "status",
                "data": {"description": description, "done": done},
            }
        )


def _require_skills_model():
    """Ensure OpenWebUI Skills model APIs are available."""
    if Skills is None or SkillForm is None or SkillMeta is None:
        raise RuntimeError("skills_model_unavailable")


def _error_message(e: Exception) -> str:
    """Map internal sentinel errors to user-friendly messages."""
    if str(e) == "skills_model_unavailable":
        return "OpenWebUI Skills model is unavailable in this runtime."
    return str(e)


def _user_skills(user_id: str, access: str = "read") -> List[Any]:
    """Load user-scoped skills using OpenWebUI Skills model."""
    return Skills.get_skills_by_user_id(user_id, access) or []


def _find_skill(
    user_id: str,
    skill_id: str = "",
    name: str = "",
) -> Optional[Any]:
    """Find a skill by id or case-insensitive name within user scope."""
    skills = _user_skills(user_id, "read")
    target_id = (skill_id or "").strip()
    target_name = (name or "").strip().lower()

    for skill in skills:
        sid = str(getattr(skill, "id", "") or "")
        sname = str(getattr(skill, "name", "") or "")
        if target_id and sid == target_id:
            return skill
        if target_name and sname.lower() == target_name:
            return skill
    return None


class Tools:
    """OpenWebUI native tools for simple skill lifecycle management."""

    class Valves(BaseModel):
        """Configurable plugin valves."""

        SHOW_STATUS: bool = Field(
            default=True,
            description="Whether to show operation status updates.",
        )
        ALLOW_OVERWRITE_ON_CREATE: bool = Field(
            default=True,
            description="Allow create_skill to overwrite same-name skill by default.",
        )

    def __init__(self):
        """Initialize plugin valves."""
        self.valves = self.Valves()

    async def list_skills(
        self,
        include_content: bool = False,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """List current user's OpenWebUI skills."""
        user_id = _get_user_id(__user__)

        try:
            _require_skills_model()
            if not user_id:
                raise ValueError("User context is required.")

            await _emit_status(self.valves, __event_emitter__, "Listing your skills...")

            skills = _user_skills(user_id, "read")
            rows = []
            for skill in skills:
                row = {
                    "id": str(getattr(skill, "id", "") or ""),
                    "name": getattr(skill, "name", ""),
                    "description": getattr(skill, "description", ""),
                    "is_active": bool(getattr(skill, "is_active", True)),
                    "updated_at": str(getattr(skill, "updated_at", "") or ""),
                }
                if include_content:
                    row["content"] = getattr(skill, "content", "")
                rows.append(row)

            rows.sort(key=lambda x: (x.get("name") or "").lower())
            active_count = sum(1 for row in rows if row.get("is_active"))

            await _emit_status(
                self.valves,
                __event_emitter__,
                f"Found {len(rows)} skills ({active_count} active).",
                done=True,
            )
            return {"count": len(rows), "skills": rows}
        except Exception as e:
            msg = _error_message(e)
            await _emit_status(self.valves, __event_emitter__, msg, done=True)
            return {"error": msg}

    async def show_skill(
        self,
        skill_id: str = "",
        name: str = "",
        include_content: bool = True,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Show one skill by id or name."""
        user_id = _get_user_id(__user__)

        try:
            _require_skills_model()
            if not user_id:
                raise ValueError("User context is required.")

            await _emit_status(
                self.valves, __event_emitter__, "Reading skill details..."
            )

            skill = _find_skill(user_id=user_id, skill_id=skill_id, name=name)
            if not skill:
                raise ValueError("Skill not found.")

            result = {
                "id": str(getattr(skill, "id", "") or ""),
                "name": getattr(skill, "name", ""),
                "description": getattr(skill, "description", ""),
                "is_active": bool(getattr(skill, "is_active", True)),
                "updated_at": str(getattr(skill, "updated_at", "") or ""),
            }
            if include_content:
                result["content"] = getattr(skill, "content", "")

            skill_name = result.get("name") or result.get("id") or "unknown"
            await _emit_status(
                self.valves,
                __event_emitter__,
                f"Loaded skill: {skill_name}.",
                done=True,
            )
            return result
        except Exception as e:
            msg = _error_message(e)
            await _emit_status(self.valves, __event_emitter__, msg, done=True)
            return {"error": msg}

    async def create_skill(
        self,
        name: str,
        description: str = "",
        content: str = "",
        overwrite: bool = True,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Create a new skill, or update same-name skill when overwrite is enabled."""
        user_id = _get_user_id(__user__)

        try:
            _require_skills_model()
            if not user_id:
                raise ValueError("User context is required.")

            skill_name = (name or "").strip()
            if not skill_name:
                raise ValueError("Skill name is required.")

            await _emit_status(self.valves, __event_emitter__, "Creating skill...")

            existing = _find_skill(user_id=user_id, name=skill_name)
            allow_overwrite = overwrite or self.valves.ALLOW_OVERWRITE_ON_CREATE

            final_description = (description or skill_name).strip()
            final_content = (content or final_description).strip()

            if existing:
                if not allow_overwrite:
                    return {
                        "error": f"Skill already exists: {skill_name}",
                        "hint": "Use overwrite=true to update existing skill.",
                    }

                sid = str(getattr(existing, "id", "") or "")
                updated = Skills.update_skill_by_id(
                    sid,
                    {
                        "name": skill_name,
                        "description": final_description,
                        "content": final_content,
                        "is_active": False,
                    },
                )
                await _emit_status(
                    self.valves,
                    __event_emitter__,
                    f"Updated existing skill: {skill_name}.",
                    done=True,
                )
                return {
                    "success": True,
                    "action": "updated",
                    "id": str(getattr(updated, "id", "") or sid),
                    "name": skill_name,
                    "is_active": False,
                    "message": "The skill was saved as inactive. Review it and enable it manually if it is safe.",
                }

            new_skill = Skills.insert_new_skill(
                user_id=user_id,
                form_data=SkillForm(
                    id=str(uuid.uuid4()),
                    name=skill_name,
                    description=final_description,
                    content=final_content,
                    meta=SkillMeta(),
                    is_active=False,
                ),
            )

            await _emit_status(
                self.valves,
                __event_emitter__,
                f"Created skill: {skill_name}.",
                done=True,
            )
            return {
                "success": True,
                "action": "created",
                "id": str(getattr(new_skill, "id", "") or ""),
                "name": skill_name,
                "is_active": False,
                "message": "The skill was saved as inactive. Review it and enable it manually if it is safe.",
            }
        except Exception as e:
            msg = _error_message(e)
            await _emit_status(self.valves, __event_emitter__, msg, done=True)
            logger.error(f"create_skill failed: {msg}", exc_info=True)
            return {"error": msg}

    async def update_skill(
        self,
        skill_id: str = "",
        name: str = "",
        new_name: str = "",
        description: str = "",
        content: str = "",
        is_active: Optional[bool] = None,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Modify an existing skill by updating one or more fields.

        Locate skill by `skill_id` or `name` (case-insensitive). Update any of:
        - `new_name`: Rename the skill (checked for name uniqueness)
        - `description`: Update skill description
        - `content`: Modify skill code/content
        - `is_active`: Enable or disable the skill

        Returns updated skill info and list of modified fields.
        """
        user_id = _get_user_id(__user__)

        try:
            _require_skills_model()
            if not user_id:
                raise ValueError("User context is required.")

            await _emit_status(self.valves, __event_emitter__, "Updating skill...")

            skill = _find_skill(user_id=user_id, skill_id=skill_id, name=name)
            if not skill:
                raise ValueError("Skill not found.")

            # Get skill ID early for collision detection
            sid = str(getattr(skill, "id", "") or "")

            updates: Dict[str, Any] = {}
            if new_name.strip():
                # Check for name collision with other skills
                new_name_clean = new_name.strip()
                # Check if another skill already has this name (case-insensitive)
                for other_skill in _user_skills(user_id, "read"):
                    other_id = str(getattr(other_skill, "id", "") or "")
                    other_name = str(getattr(other_skill, "name", "") or "")
                    # Skip the current skill being updated
                    if other_id == sid:
                        continue
                    if other_name.lower() == new_name_clean.lower():
                        return {
                            "error": f'Another skill already has the name "{new_name_clean}".',
                            "hint": "Choose a different name.",
                        }

                updates["name"] = new_name_clean
            if description.strip():
                updates["description"] = description.strip()
            if content.strip():
                updates["content"] = content.strip()
            if is_active is not None:
                updates["is_active"] = bool(is_active)

            if not updates:
                raise ValueError("No update fields provided.")

            updated = Skills.update_skill_by_id(sid, updates)
            updated_name = str(
                getattr(updated, "name", "")
                or updates.get("name")
                or getattr(skill, "name", "")
                or sid
            )

            await _emit_status(
                self.valves,
                __event_emitter__,
                f"Updated skill: {updated_name}.",
                done=True,
            )
            return {
                "success": True,
                "id": str(getattr(updated, "id", "") or sid),
                "name": str(
                    getattr(updated, "name", "")
                    or updates.get("name")
                    or getattr(skill, "name", "")
                ),
                "updated_fields": list(updates.keys()),
            }
        except Exception as e:
            msg = _error_message(e)
            await _emit_status(self.valves, __event_emitter__, msg, done=True)
            return {"error": msg}
