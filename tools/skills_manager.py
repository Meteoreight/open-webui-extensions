"""
title: OpenWebUI Skills Manager Tool
author: Fu-Jie
author_url: https://github.com/Fu-Jie/openwebui-extensions
funding_url: https://github.com/open-webui
version: 0.3.0
openwebui_id: b4bce8e4-08e7-4f90-bea7-dc31d463a0bb
requirements:
description: Standalone OpenWebUI tool for managing native Workspace Skills (list/show/create/update/delete) for any model.
"""

import asyncio
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


BASE_TRANSLATIONS = {
    "status_listing": "Listing your skills...",
    "status_showing": "Reading skill details...",
    "status_creating": "Creating skill...",
    "status_updating": "Updating skill...",
    "status_deleting": "Deleting skill...",
    "status_done": "Done.",
    "status_list_done": "Found {count} skills ({active_count} active).",
    "status_show_done": "Loaded skill: {name}.",
    "status_create_done": "Created skill: {name}.",
    "status_create_overwrite_done": "Updated existing skill: {name}.",
    "status_update_done": "Updated skill: {name}.",
    "status_delete_done": "Deleted skill: {name}.",
    "err_unavailable": "OpenWebUI Skills model is unavailable in this runtime.",
    "err_user_required": "User context is required.",
    "err_name_required": "Skill name is required.",
    "err_not_found": "Skill not found.",
    "err_no_update_fields": "No update fields provided.",
    "msg_created": "Skill created successfully.",
    "msg_updated": "Skill updated successfully.",
    "msg_deleted": "Skill deleted successfully.",
}

TRANSLATIONS = {
    "en-US": BASE_TRANSLATIONS,
    "zh-CN": {
        "status_listing": "正在列出你的技能...",
        "status_showing": "正在读取技能详情...",
        "status_creating": "正在创建技能...",
        "status_updating": "正在更新技能...",
        "status_deleting": "正在删除技能...",
        "status_done": "已完成。",
        "status_list_done": "已找到 {count} 个技能（启用 {active_count} 个）。",
        "status_show_done": "已加载技能：{name}。",
        "status_create_done": "技能创建完成：{name}。",
        "status_create_overwrite_done": "已更新同名技能：{name}。",
        "status_update_done": "技能更新完成：{name}。",
        "status_delete_done": "技能删除完成：{name}。",
        "err_unavailable": "当前运行环境不可用 OpenWebUI Skills 模型。",
        "err_user_required": "需要用户上下文。",
        "err_name_required": "技能名称不能为空。",
        "err_not_found": "未找到技能。",
        "err_no_update_fields": "未提供可更新字段。",
        "msg_created": "技能创建成功。",
        "msg_updated": "技能更新成功。",
        "msg_deleted": "技能删除成功。",
    },
    "zh-TW": {
        "status_listing": "正在列出你的技能...",
        "status_showing": "正在讀取技能詳情...",
        "status_creating": "正在建立技能...",
        "status_updating": "正在更新技能...",
        "status_deleting": "正在刪除技能...",
        "status_done": "已完成。",
        "status_list_done": "已找到 {count} 個技能（啟用 {active_count} 個）。",
        "status_show_done": "已載入技能：{name}。",
        "status_create_done": "技能建立完成：{name}。",
        "status_create_overwrite_done": "已更新同名技能：{name}。",
        "status_update_done": "技能更新完成：{name}。",
        "status_delete_done": "技能刪除完成：{name}。",
        "err_unavailable": "目前執行環境不可用 OpenWebUI Skills 模型。",
        "err_user_required": "需要使用者上下文。",
        "err_name_required": "技能名稱不能為空。",
        "err_not_found": "未找到技能。",
        "err_no_update_fields": "未提供可更新欄位。",
        "msg_created": "技能建立成功。",
        "msg_updated": "技能更新成功。",
        "msg_deleted": "技能刪除成功。",
    },
    "zh-HK": {
        "status_listing": "正在列出你的技能...",
        "status_showing": "正在讀取技能詳情...",
        "status_creating": "正在建立技能...",
        "status_updating": "正在更新技能...",
        "status_deleting": "正在刪除技能...",
        "status_done": "已完成。",
        "status_list_done": "已找到 {count} 個技能（啟用 {active_count} 個）。",
        "status_show_done": "已載入技能：{name}。",
        "status_create_done": "技能建立完成：{name}。",
        "status_create_overwrite_done": "已更新同名技能：{name}。",
        "status_update_done": "技能更新完成：{name}。",
        "status_delete_done": "技能刪除完成：{name}。",
        "err_unavailable": "目前執行環境不可用 OpenWebUI Skills 模型。",
        "err_user_required": "需要使用者上下文。",
        "err_name_required": "技能名稱不能為空。",
        "err_not_found": "未找到技能。",
        "err_no_update_fields": "未提供可更新欄位。",
        "msg_created": "技能建立成功。",
        "msg_updated": "技能更新成功。",
        "msg_deleted": "技能刪除成功。",
    },
    "ja-JP": {
        "status_listing": "スキル一覧を取得しています...",
        "status_showing": "スキル詳細を読み込み中...",
        "status_creating": "スキルを作成中...",
        "status_updating": "スキルを更新中...",
        "status_deleting": "スキルを削除中...",
        "status_done": "完了しました。",
        "status_list_done": "{count} 件のスキルが見つかりました（有効: {active_count} 件）。",
        "status_show_done": "スキルを読み込みました: {name}。",
        "status_create_done": "スキルを作成しました: {name}。",
        "status_create_overwrite_done": "同名スキルを更新しました: {name}。",
        "status_update_done": "スキルを更新しました: {name}。",
        "status_delete_done": "スキルを削除しました: {name}。",
        "err_unavailable": "この実行環境では OpenWebUI Skills モデルを利用できません。",
        "err_user_required": "ユーザーコンテキストが必要です。",
        "err_name_required": "スキル名は必須です。",
        "err_not_found": "スキルが見つかりません。",
        "err_no_update_fields": "更新する項目が指定されていません。",
        "msg_created": "スキルを作成しました。",
        "msg_updated": "スキルを更新しました。",
        "msg_deleted": "スキルを削除しました。",
    },
    "ko-KR": {
        "status_listing": "스킬 목록을 불러오는 중...",
        "status_showing": "스킬 상세 정보를 읽는 중...",
        "status_creating": "스킬 생성 중...",
        "status_updating": "스킬 업데이트 중...",
        "status_deleting": "스킬 삭제 중...",
        "status_done": "완료되었습니다.",
        "status_list_done": "스킬 {count}개를 찾았습니다(활성 {active_count}개).",
        "status_show_done": "스킬을 불러왔습니다: {name}.",
        "status_create_done": "스킬 생성 완료: {name}.",
        "status_create_overwrite_done": "동일 이름 스킬 업데이트 완료: {name}.",
        "status_update_done": "스킬 업데이트 완료: {name}.",
        "status_delete_done": "스킬 삭제 완료: {name}.",
        "err_unavailable": "현재 런타임에서 OpenWebUI Skills 모델을 사용할 수 없습니다.",
        "err_user_required": "사용자 컨텍스트가 필요합니다.",
        "err_name_required": "스킬 이름은 필수입니다.",
        "err_not_found": "스킬을 찾을 수 없습니다.",
        "err_no_update_fields": "업데이트할 필드가 제공되지 않았습니다.",
        "msg_created": "스킬이 생성되었습니다.",
        "msg_updated": "스킬이 업데이트되었습니다.",
        "msg_deleted": "스킬이 삭제되었습니다.",
    },
    "fr-FR": {
        "status_listing": "Liste des skills en cours...",
        "status_showing": "Lecture des détails du skill...",
        "status_creating": "Création du skill...",
        "status_updating": "Mise à jour du skill...",
        "status_deleting": "Suppression du skill...",
        "status_done": "Terminé.",
        "status_list_done": "{count} skills trouvés ({active_count} actifs).",
        "status_show_done": "Skill chargé : {name}.",
        "status_create_done": "Skill créé : {name}.",
        "status_create_overwrite_done": "Skill existant mis à jour : {name}.",
        "status_update_done": "Skill mis à jour : {name}.",
        "status_delete_done": "Skill supprimé : {name}.",
        "err_unavailable": "Le modèle OpenWebUI Skills n'est pas disponible dans cet environnement.",
        "err_user_required": "Le contexte utilisateur est requis.",
        "err_name_required": "Le nom du skill est requis.",
        "err_not_found": "Skill introuvable.",
        "err_no_update_fields": "Aucun champ à mettre à jour n'a été fourni.",
        "msg_created": "Skill créé avec succès.",
        "msg_updated": "Skill mis à jour avec succès.",
        "msg_deleted": "Skill supprimé avec succès.",
    },
    "de-DE": {
        "status_listing": "Deine Skills werden aufgelistet...",
        "status_showing": "Skill-Details werden gelesen...",
        "status_creating": "Skill wird erstellt...",
        "status_updating": "Skill wird aktualisiert...",
        "status_deleting": "Skill wird gelöscht...",
        "status_done": "Fertig.",
        "status_list_done": "{count} Skills gefunden ({active_count} aktiv).",
        "status_show_done": "Skill geladen: {name}.",
        "status_create_done": "Skill erstellt: {name}.",
        "status_create_overwrite_done": "Bestehender Skill aktualisiert: {name}.",
        "status_update_done": "Skill aktualisiert: {name}.",
        "status_delete_done": "Skill gelöscht: {name}.",
        "err_unavailable": "Das OpenWebUI-Skills-Modell ist in dieser Laufzeit nicht verfügbar.",
        "err_user_required": "Benutzerkontext ist erforderlich.",
        "err_name_required": "Skill-Name ist erforderlich.",
        "err_not_found": "Skill nicht gefunden.",
        "err_no_update_fields": "Keine zu aktualisierenden Felder angegeben.",
        "msg_created": "Skill erfolgreich erstellt.",
        "msg_updated": "Skill erfolgreich aktualisiert.",
        "msg_deleted": "Skill erfolgreich gelöscht.",
    },
    "es-ES": {
        "status_listing": "Listando tus skills...",
        "status_showing": "Leyendo detalles del skill...",
        "status_creating": "Creando skill...",
        "status_updating": "Actualizando skill...",
        "status_deleting": "Eliminando skill...",
        "status_done": "Hecho.",
        "status_list_done": "Se encontraron {count} skills ({active_count} activos).",
        "status_show_done": "Skill cargado: {name}.",
        "status_create_done": "Skill creado: {name}.",
        "status_create_overwrite_done": "Skill existente actualizado: {name}.",
        "status_update_done": "Skill actualizado: {name}.",
        "status_delete_done": "Skill eliminado: {name}.",
        "err_unavailable": "El modelo OpenWebUI Skills no está disponible en este entorno.",
        "err_user_required": "Se requiere contexto de usuario.",
        "err_name_required": "Se requiere el nombre del skill.",
        "err_not_found": "Skill no encontrado.",
        "err_no_update_fields": "No se proporcionaron campos para actualizar.",
        "msg_created": "Skill creado correctamente.",
        "msg_updated": "Skill actualizado correctamente.",
        "msg_deleted": "Skill eliminado correctamente.",
    },
    "it-IT": {
        "status_listing": "Elenco delle skill in corso...",
        "status_showing": "Lettura dei dettagli della skill...",
        "status_creating": "Creazione della skill...",
        "status_updating": "Aggiornamento della skill...",
        "status_deleting": "Eliminazione della skill...",
        "status_done": "Fatto.",
        "status_list_done": "Trovate {count} skill ({active_count} attive).",
        "status_show_done": "Skill caricata: {name}.",
        "status_create_done": "Skill creata: {name}.",
        "status_create_overwrite_done": "Skill esistente aggiornata: {name}.",
        "status_update_done": "Skill aggiornata: {name}.",
        "status_delete_done": "Skill eliminata: {name}.",
        "err_unavailable": "Il modello OpenWebUI Skills non è disponibile in questo runtime.",
        "err_user_required": "È richiesto il contesto utente.",
        "err_name_required": "Il nome della skill è obbligatorio.",
        "err_not_found": "Skill non trovata.",
        "err_no_update_fields": "Nessun campo da aggiornare fornito.",
        "msg_created": "Skill creata con successo.",
        "msg_updated": "Skill aggiornata con successo.",
        "msg_deleted": "Skill eliminata con successo.",
    },
    "vi-VN": {
        "status_listing": "Đang liệt kê kỹ năng của bạn...",
        "status_showing": "Đang đọc chi tiết kỹ năng...",
        "status_creating": "Đang tạo kỹ năng...",
        "status_updating": "Đang cập nhật kỹ năng...",
        "status_deleting": "Đang xóa kỹ năng...",
        "status_done": "Hoàn tất.",
        "status_list_done": "Đã tìm thấy {count} kỹ năng ({active_count} đang bật).",
        "status_show_done": "Đã tải kỹ năng: {name}.",
        "status_create_done": "Tạo kỹ năng hoàn tất: {name}.",
        "status_create_overwrite_done": "Đã cập nhật kỹ năng cùng tên: {name}.",
        "status_update_done": "Cập nhật kỹ năng hoàn tất: {name}.",
        "status_delete_done": "Xóa kỹ năng hoàn tất: {name}.",
        "err_unavailable": "Mô hình OpenWebUI Skills không khả dụng trong môi trường hiện tại.",
        "err_user_required": "Cần có ngữ cảnh người dùng.",
        "err_name_required": "Tên kỹ năng là bắt buộc.",
        "err_not_found": "Không tìm thấy kỹ năng.",
        "err_no_update_fields": "Không có trường nào để cập nhật.",
        "msg_created": "Tạo kỹ năng thành công.",
        "msg_updated": "Cập nhật kỹ năng thành công.",
        "msg_deleted": "Xóa kỹ năng thành công.",
    },
    "id-ID": {
        "status_listing": "Sedang menampilkan daftar skill Anda...",
        "status_showing": "Sedang membaca detail skill...",
        "status_creating": "Sedang membuat skill...",
        "status_updating": "Sedang memperbarui skill...",
        "status_deleting": "Sedang menghapus skill...",
        "status_done": "Selesai.",
        "status_list_done": "Ditemukan {count} skill ({active_count} aktif).",
        "status_show_done": "Skill dimuat: {name}.",
        "status_create_done": "Skill berhasil dibuat: {name}.",
        "status_create_overwrite_done": "Skill dengan nama sama berhasil diperbarui: {name}.",
        "status_update_done": "Skill berhasil diperbarui: {name}.",
        "status_delete_done": "Skill berhasil dihapus: {name}.",
        "err_unavailable": "Model OpenWebUI Skills tidak tersedia di runtime ini.",
        "err_user_required": "Konteks pengguna diperlukan.",
        "err_name_required": "Nama skill wajib diisi.",
        "err_not_found": "Skill tidak ditemukan.",
        "err_no_update_fields": "Tidak ada field pembaruan yang diberikan.",
        "msg_created": "Skill berhasil dibuat.",
        "msg_updated": "Skill berhasil diperbarui.",
        "msg_deleted": "Skill berhasil dihapus.",
    },
}

FALLBACK_MAP = {
    "zh": "zh-CN",
    "zh-TW": "zh-TW",
    "zh-HK": "zh-HK",
    "en": "en-US",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "fr": "fr-FR",
    "de": "de-DE",
    "es": "es-ES",
    "it": "it-IT",
    "vi": "vi-VN",
    "id": "id-ID",
}


def _resolve_language(user_language: str) -> str:
    """Normalize user language code to a supported translation key."""
    value = str(user_language or "").strip()
    if not value:
        return "en-US"

    normalized = value.replace("_", "-")

    if normalized in TRANSLATIONS:
        return normalized

    lower_to_lang = {k.lower(): k for k in TRANSLATIONS.keys()}
    if normalized.lower() in lower_to_lang:
        return lower_to_lang[normalized.lower()]

    if normalized in FALLBACK_MAP:
        return FALLBACK_MAP[normalized]

    lower_fallback = {k.lower(): v for k, v in FALLBACK_MAP.items()}
    if normalized.lower() in lower_fallback:
        return lower_fallback[normalized.lower()]

    base = normalized.split("-")[0].lower()
    return lower_fallback.get(base, "en-US")


def _t(lang: str, key: str, **kwargs) -> str:
    """Return translated text for key with safe formatting."""
    lang_key = _resolve_language(lang)
    text = TRANSLATIONS.get(lang_key, TRANSLATIONS["en-US"]).get(
        key, TRANSLATIONS["en-US"].get(key, key)
    )
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text


async def _get_user_context(
    __user__: Optional[dict],
    __event_call__: Optional[Any] = None,
    __request__: Optional[Any] = None,
) -> Dict[str, str]:
    """Extract robust user context with frontend language fallback."""
    if isinstance(__user__, (list, tuple)):
        user_data = __user__[0] if __user__ else {}
    elif isinstance(__user__, dict):
        user_data = __user__
    else:
        user_data = {}

    user_language = user_data.get("language", "en-US")

    if __request__ and hasattr(__request__, "headers"):
        accept_lang = __request__.headers.get("accept-language", "")
        if accept_lang:
            user_language = accept_lang.split(",")[0].split(";")[0]

    if __event_call__:
        try:
            js_code = """
                try {
                    return (
                        document.documentElement.lang ||
                        localStorage.getItem('locale') ||
                        localStorage.getItem('language') ||
                        navigator.language ||
                        'en-US'
                    );
                } catch (e) {
                    return 'en-US';
                }
            """
            frontend_lang = await asyncio.wait_for(
                __event_call__({"type": "execute", "data": {"code": js_code}}),
                timeout=2.0,
            )
            if frontend_lang and isinstance(frontend_lang, str):
                user_language = frontend_lang
        except Exception as e:
            logger.warning(f"Failed to retrieve frontend language: {e}")

    return {
        "user_id": str(user_data.get("id", "")).strip(),
        "user_name": user_data.get("name", "User"),
        "user_language": user_language,
    }



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
        __event_call__: Optional[Any] = None,
        __request__: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """List current user's OpenWebUI skills."""
        user_ctx = await _get_user_context(__user__, __event_call__, __request__)
        lang = user_ctx["user_language"]
        user_id = user_ctx["user_id"]

        try:
            _require_skills_model()
            if not user_id:
                raise ValueError(_t(lang, "err_user_required"))

            await _emit_status(self.valves, __event_emitter__, _t(lang, "status_listing"))

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

            await _emit_status(self.valves, __event_emitter__, _t(
                    lang,
                    "status_list_done",
                    count=len(rows),
                    active_count=active_count,
                ),
                done=True,
            )
            return {"count": len(rows), "skills": rows}
        except Exception as e:
            msg = (
                _t(lang, "err_unavailable")
                if str(e) == "skills_model_unavailable"
                else str(e)
            )
            await _emit_status(self.valves, __event_emitter__, msg, done=True)
            return {"error": msg}

    async def show_skill(
        self,
        skill_id: str = "",
        name: str = "",
        include_content: bool = True,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Any] = None,
        __event_call__: Optional[Any] = None,
        __request__: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Show one skill by id or name."""
        user_ctx = await _get_user_context(__user__, __event_call__, __request__)
        lang = user_ctx["user_language"]
        user_id = user_ctx["user_id"]

        try:
            _require_skills_model()
            if not user_id:
                raise ValueError(_t(lang, "err_user_required"))

            await _emit_status(self.valves, __event_emitter__, _t(lang, "status_showing"))

            skill = _find_skill(user_id=user_id, skill_id=skill_id, name=name)
            if not skill:
                raise ValueError(_t(lang, "err_not_found"))

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
            await _emit_status(self.valves, __event_emitter__, _t(lang, "status_show_done", name=skill_name),
                done=True,
            )
            return result
        except Exception as e:
            msg = (
                _t(lang, "err_unavailable")
                if str(e) == "skills_model_unavailable"
                else str(e)
            )
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
        __event_call__: Optional[Any] = None,
        __request__: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Create a new skill, or update same-name skill when overwrite is enabled."""
        user_ctx = await _get_user_context(__user__, __event_call__, __request__)
        lang = user_ctx["user_language"]
        user_id = user_ctx["user_id"]

        try:
            _require_skills_model()
            if not user_id:
                raise ValueError(_t(lang, "err_user_required"))

            skill_name = (name or "").strip()
            if not skill_name:
                raise ValueError(_t(lang, "err_name_required"))

            await _emit_status(self.valves, __event_emitter__, _t(lang, "status_creating"))

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
                        "is_active": True,
                    },
                )
                await _emit_status(self.valves, __event_emitter__, _t(lang, "status_create_overwrite_done", name=skill_name),
                    done=True,
                )
                return {
                    "success": True,
                    "action": "updated",
                    "id": str(getattr(updated, "id", "") or sid),
                    "name": skill_name,
                }

            new_skill = Skills.insert_new_skill(
                user_id=user_id,
                form_data=SkillForm(
                    id=str(uuid.uuid4()),
                    name=skill_name,
                    description=final_description,
                    content=final_content,
                    meta=SkillMeta(),
                    is_active=True,
                ),
            )

            await _emit_status(self.valves, __event_emitter__, _t(lang, "status_create_done", name=skill_name),
                done=True,
            )
            return {
                "success": True,
                "action": "created",
                "id": str(getattr(new_skill, "id", "") or ""),
                "name": skill_name,
            }
        except Exception as e:
            msg = (
                _t(lang, "err_unavailable")
                if str(e) == "skills_model_unavailable"
                else str(e)
            )
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
        __event_call__: Optional[Any] = None,
        __request__: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Modify an existing skill by updating one or more fields.

        Locate skill by `skill_id` or `name` (case-insensitive). Update any of:
        - `new_name`: Rename the skill (checked for name uniqueness)
        - `description`: Update skill description
        - `content`: Modify skill code/content
        - `is_active`: Enable or disable the skill

        Returns updated skill info and list of modified fields.
        """
        user_ctx = await _get_user_context(__user__, __event_call__, __request__)
        lang = user_ctx["user_language"]
        user_id = user_ctx["user_id"]

        try:
            _require_skills_model()
            if not user_id:
                raise ValueError(_t(lang, "err_user_required"))

            await _emit_status(self.valves, __event_emitter__, _t(lang, "status_updating"))

            skill = _find_skill(user_id=user_id, skill_id=skill_id, name=name)
            if not skill:
                raise ValueError(_t(lang, "err_not_found"))

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
                            "hint": "Choose a different name or delete the conflicting skill first.",
                        }

                updates["name"] = new_name_clean
            if description.strip():
                updates["description"] = description.strip()
            if content.strip():
                updates["content"] = content.strip()
            if is_active is not None:
                updates["is_active"] = bool(is_active)

            if not updates:
                raise ValueError(_t(lang, "err_no_update_fields"))

            updated = Skills.update_skill_by_id(sid, updates)
            updated_name = str(
                getattr(updated, "name", "")
                or updates.get("name")
                or getattr(skill, "name", "")
                or sid
            )

            await _emit_status(self.valves, __event_emitter__, _t(lang, "status_update_done", name=updated_name),
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
            msg = (
                _t(lang, "err_unavailable")
                if str(e) == "skills_model_unavailable"
                else str(e)
            )
            await _emit_status(self.valves, __event_emitter__, msg, done=True)
            return {"error": msg}

    async def delete_skill(
        self,
        skill_id: str = "",
        name: str = "",
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Any] = None,
        __event_call__: Optional[Any] = None,
        __request__: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Delete one skill by id or name."""
        user_ctx = await _get_user_context(__user__, __event_call__, __request__)
        lang = user_ctx["user_language"]
        user_id = user_ctx["user_id"]

        try:
            _require_skills_model()
            if not user_id:
                raise ValueError(_t(lang, "err_user_required"))

            await _emit_status(self.valves, __event_emitter__, _t(lang, "status_deleting"))

            skill = _find_skill(user_id=user_id, skill_id=skill_id, name=name)
            if not skill:
                raise ValueError(_t(lang, "err_not_found"))

            sid = str(getattr(skill, "id", "") or "")
            sname = str(getattr(skill, "name", "") or "")
            Skills.delete_skill_by_id(sid)
            deleted_name = sname or sid or "unknown"

            await _emit_status(self.valves, __event_emitter__, _t(lang, "status_delete_done", name=deleted_name),
                done=True,
            )
            return {
                "success": True,
                "id": sid,
                "name": sname,
            }
        except Exception as e:
            msg = (
                _t(lang, "err_unavailable")
                if str(e) == "skills_model_unavailable"
                else str(e)
            )
            await _emit_status(self.valves, __event_emitter__, msg, done=True)
            return {"error": msg}
