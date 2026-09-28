"""B1 (P″) passphrase persistence + type-discrimination lock (RED-first).

DoD pinned by @架构 seq3900 + @需求 seq3904:
  - key 型: passphrase -> secret_enc (key 型现闲置), key_enc keeps the bare key.
  - password 型: non-empty passphrase -> explicit rejection (4xx-equivalent), NOT silent drop.
  - cross matrix: key 型 rejects `secret`; password 型 rejects `key`.
  - invalid type: `type ∉ {password, key}` -> explicit reject (create ∪ edit).
  - type switch: clear the other column and re-validate the new type's required field.

DoD① layer/status pinned by @架构 seq3906: explicit reject = HTTP 400 via the
existing BadRequestError, decided in the *service* layer (Update's effective type
depends on the stored cred.type). Matrix (DoD②) rejects are asserted the same way
(service-layer BadRequestError -> 400), so a pydantic-layer 422 cannot silently
mask a layer drift.

Baseline tip 4efc97e: passphrase is silently dropped, no type discrimination,
type switch does not clear the other column -> the DoD cases here are RED.
The empty-value cases (`""`/None = "not provided", @架构 seq3912) are
NON-REGRESSION GUARDS: green at baseline, must stay green so the B1 fix does not
over-reject the FE's always-carried empty-string payload.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import BadRequestError
from app.core.security import decrypt_secret
from app.schemas.asset import CredentialCreate, CredentialUpdate
from app.services import asset_service

REJECT: tuple[type[BaseException], ...] = (BadRequestError,)


# ----------------------------------------------------------------- helpers


def make_user(is_admin=True, visible=None):
    return SimpleNamespace(
        id=1,
        username="admin" if is_admin else "operator",
        is_admin=is_admin,
        visible_group_ids=visible if visible is not None else [1, 2],
    )


def make_host(**over):
    base = dict(
        id=10, hostname="web-01", ip="10.0.0.1", os_type="linux", os_version="Ubuntu 22.04",
        group_id=1, env="prod", tags=[], sensitivity_level="normal", status="offline",
        connector="agent", agent_id=None, agent_version="", last_heartbeat_at=None,
        remark="", created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    base.update(over)
    return SimpleNamespace(**base)


class FakeDb:
    def flush(self):
        pass

    def commit(self):
        pass

    def delete(self, obj):
        pass

    def scalar(self, stmt):
        return 0

    def query(self, model):
        return SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(first=lambda: None))


class FakeHostRepo:
    def __init__(self, get=None):
        self._get = get

    def get(self, _id):
        return self._get


class FakeGroupRepo:
    def __init__(self, groups=None):
        self._groups = groups or []

    def all_tree(self):
        return list(self._groups)

    def get(self, _id):
        return None


class FakeCredRepo:
    def __init__(self, by_host=None, get=None):
        self._by_host = by_host
        self._get = get
        self.added = []

    def by_host(self, _id):
        return self._by_host

    def get(self, _id):
        return self._get

    def add(self, obj):
        self.added.append(obj)
        obj.id = 7
        return obj


def patch(monkeypatch, host_repo=None, group_repo=None, cred_repo=None):
    monkeypatch.setattr(asset_service, "HostRepository", lambda db: host_repo or FakeHostRepo())
    monkeypatch.setattr(asset_service, "GroupRepository", lambda db: group_repo or FakeGroupRepo())
    monkeypatch.setattr(asset_service, "CredentialRepository", lambda db: cred_repo or FakeCredRepo())


# ------------------------------------------------- A. key 型 passphrase 持久化


def test_b1_key_passphrase_persisted_in_secret_enc(monkeypatch):
    """(P″): key 型 passphrase 存 secret_enc；key_enc 仍为裸 key。"""
    repo = FakeCredRepo()
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()), cred_repo=repo)
    asset_service.create_credential(
        FakeDb(), make_user(),
        CredentialCreate(host_id=10, type="key", username="root",
                         key="PRIV-KEY", passphrase="p@ss"),
    )
    stored = repo.added[0]
    assert stored.key_enc and decrypt_secret(stored.key_enc) == "PRIV-KEY"
    assert stored.secret_enc, "key 型 passphrase must be persisted (not silently dropped)"
    assert decrypt_secret(stored.secret_enc) == "p@ss"


def test_b1_key_passphrase_roundtrip_via_update(monkeypatch):
    """PATCH key 型凭据补 passphrase -> secret_enc round-trip。"""
    cred = SimpleNamespace(id=7, host_id=10, type="key", username="root",
                           secret_enc=None, key_enc="enc:priv", key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    asset_service.update_credential(
        FakeDb(), make_user(), 7, CredentialUpdate(passphrase="p@ss"),
    )
    assert cred.secret_enc, "passphrase update must persist, not drop"
    assert decrypt_secret(cred.secret_enc) == "p@ss"


# ------------------------------------------- B/C/D. 类型判别（显式拒绝，非静默）


def test_b1_password_type_rejects_passphrase(monkeypatch):
    """password 型带非空 passphrase -> 显式拒绝 400（DoD①·service 层）。"""
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()), cred_repo=FakeCredRepo())
    with pytest.raises(BadRequestError):
        asset_service.create_credential(
            FakeDb(), make_user(),
            CredentialCreate(host_id=10, type="password", username="root",
                             secret="s3cret", passphrase="p@ss"),
        )


def test_b1_update_password_rejects_passphrase(monkeypatch):
    """生效类型（库内 cred.type=password）带非空 passphrase -> 显式拒绝 400。"""
    cred = SimpleNamespace(id=7, host_id=10, type="password", username="root",
                           secret_enc="enc:secret", key_enc=None, key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    with pytest.raises(BadRequestError):
        asset_service.update_credential(
            FakeDb(), make_user(), 7, CredentialUpdate(passphrase="p@ss"),
        )


def test_b1_update_switch_to_password_with_passphrase_rejected(monkeypatch):
    """同请求把类型改为 password 且带 passphrase -> 按 PATCH 后生效类型拒绝 400。"""
    cred = SimpleNamespace(id=7, host_id=10, type="key", username="root",
                           secret_enc=None, key_enc="enc:priv", key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    with pytest.raises(BadRequestError):
        asset_service.update_credential(
            FakeDb(), make_user(), 7,
            CredentialUpdate(type="password", secret="newsecret", passphrase="p@ss"),
        )


def test_b1_update_switch_to_key_accepts_passphrase(monkeypatch):
    """同请求把类型改为 key 且带 key+passphrase -> 按 PATCH 后生效类型放行并存短语。"""
    cred = SimpleNamespace(id=7, host_id=10, type="password", username="root",
                           secret_enc="enc:old", key_enc=None, key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    asset_service.update_credential(
        FakeDb(), make_user(), 7,
        CredentialUpdate(type="key", key="NEW-KEY", passphrase="p@ss"),
    )
    assert cred.type == "key"
    assert cred.key_enc and decrypt_secret(cred.key_enc) == "NEW-KEY"
    assert cred.secret_enc and decrypt_secret(cred.secret_enc) == "p@ss"


def test_b1_key_type_rejects_secret_field(monkeypatch):
    """key 型带 secret -> 拒绝（防止 secret_enc 被误读为短语）。"""
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()), cred_repo=FakeCredRepo())
    with pytest.raises(REJECT):
        asset_service.create_credential(
            FakeDb(), make_user(),
            CredentialCreate(host_id=10, type="key", username="root",
                             key="PRIV-KEY", secret="s3cret"),
        )


def test_b1_password_type_rejects_key_field(monkeypatch):
    """password 型带 key -> 拒绝。"""
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()), cred_repo=FakeCredRepo())
    with pytest.raises(REJECT):
        asset_service.create_credential(
            FakeDb(), make_user(),
            CredentialCreate(host_id=10, type="password", username="root",
                             secret="s3cret", key="PRIV-KEY"),
        )


# --------------------------------------------------- update-face cross matrix


def test_b1_update_key_type_rejects_secret_field(monkeypatch):
    """update 生效类型=key 带非空 secret -> 400（防 secret_enc 被当短语）。"""
    cred = SimpleNamespace(id=7, host_id=10, type="key", username="root",
                           secret_enc=None, key_enc="enc:priv", key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    with pytest.raises(BadRequestError):
        asset_service.update_credential(
            FakeDb(), make_user(), 7, CredentialUpdate(secret="s3cret"),
        )


def test_b1_update_password_type_rejects_key_field(monkeypatch):
    """update 生效类型=password 带非空 key -> 400。"""
    cred = SimpleNamespace(id=7, host_id=10, type="password", username="root",
                           secret_enc="enc:secret", key_enc=None, key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    with pytest.raises(BadRequestError):
        asset_service.update_credential(
            FakeDb(), make_user(), 7, CredentialUpdate(key="PRIV-KEY"),
        )


def test_b1_switch_to_key_without_passphrase_clears_secret_enc(monkeypatch):
    """→key 无 passphrase：须清 secret_enc，防旧密码被 (P″) 读成短语。"""
    cred = SimpleNamespace(id=7, host_id=10, type="password", username="root",
                           secret_enc="enc:old-password", key_enc=None, key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    asset_service.update_credential(
        FakeDb(), make_user(), 7, CredentialUpdate(type="key", key="NEW-KEY"),
    )
    assert cred.type == "key"
    assert cred.key_enc and decrypt_secret(cred.key_enc) == "NEW-KEY"
    assert cred.secret_enc is None, "stale password must not survive as a (P″) passphrase"


def test_b1_switch_to_key_requires_key(monkeypatch):
    """→key 无 key -> 400（对齐 →password 无 secret 的必填复核）。"""
    cred = SimpleNamespace(id=7, host_id=10, type="password", username="root",
                           secret_enc="enc:secret", key_enc=None, key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    with pytest.raises(BadRequestError):
        asset_service.update_credential(
            FakeDb(), make_user(), 7, CredentialUpdate(type="key"),
        )


def test_b1_switch_to_key_with_empty_passphrase_clears_secret_enc(monkeypatch):
    """变更→key＋passphrase=''（未提供）⇒ 仍清 secret_enc（FE 恒带空串可达）。"""
    cred = SimpleNamespace(id=7, host_id=10, type="password", username="root",
                           secret_enc="enc:old-password", key_enc=None, key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    asset_service.update_credential(
        FakeDb(), make_user(), 7,
        CredentialUpdate(type="key", key="NEW-KEY", passphrase=""),
    )
    assert cred.type == "key"
    assert cred.key_enc and decrypt_secret(cred.key_enc) == "NEW-KEY"
    assert cred.secret_enc is None, "empty-string passphrase is 'not provided', not 'retain'"


def test_b1_switch_to_password_with_empty_key_clears_key_enc(monkeypatch):
    """变更→password＋key=''（未提供）⇒ 清 key_enc（对向同理）。"""
    cred = SimpleNamespace(id=7, host_id=10, type="key", username="root",
                           secret_enc=None, key_enc="enc:priv", key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    asset_service.update_credential(
        FakeDb(), make_user(), 7,
        CredentialUpdate(type="password", secret="NEW-SECRET", key=""),
    )
    assert cred.type == "password"
    assert cred.key_enc is None, "empty-string key is 'not provided'; stale key_enc must clear"
    assert cred.secret_enc and decrypt_secret(cred.secret_enc) == "NEW-SECRET"


# --------------------------------------------------- empty = "not provided"


def test_b1_empty_fields_treated_as_absent_on_create(monkeypatch):
    """FE 恒带空串负载（secret/key/passphrase='') 不得触发 400（空值=未提供）。"""
    repo = FakeCredRepo()
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()), cred_repo=repo)
    asset_service.create_credential(
        FakeDb(), make_user(),
        CredentialCreate(host_id=10, type="password", username="root",
                         secret="s3cret", key="", passphrase=""),
    )
    asset_service.create_credential(
        FakeDb(), make_user(),
        CredentialCreate(host_id=10, type="key", username="root",
                         key="PRIV-KEY", secret="", passphrase=""),
    )
    password_cred, key_cred = repo.added
    assert decrypt_secret(password_cred.secret_enc) == "s3cret"
    assert key_cred.key_enc and decrypt_secret(key_cred.key_enc) == "PRIV-KEY"
    assert not key_cred.secret_enc, "empty passphrase must not be persisted"


def test_b1_empty_passphrase_on_update_is_allowed(monkeypatch):
    """update 携带 passphrase='' 视为未提供：放行且不改动既有 secret_enc。"""
    cred = SimpleNamespace(id=7, host_id=10, type="password", username="root",
                           secret_enc="enc:secret", key_enc=None, key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    asset_service.update_credential(
        FakeDb(), make_user(), 7, CredentialUpdate(passphrase="", key=""),
    )
    assert cred.secret_enc == "enc:secret"


# ------------------------------------- same-type omission = retain (not clear)


def test_b1_same_key_type_omitted_passphrase_retains_secret_enc(monkeypatch):
    """同型(key)+passphrase 缺省 ⇒ 保留既有 secret_enc（PATCH 未提供=不改）。"""
    cred = SimpleNamespace(id=7, host_id=10, type="key", username="root",
                           secret_enc="enc:existing-passphrase", key_enc="enc:priv",
                           key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    asset_service.update_credential(
        FakeDb(), make_user(), 7, CredentialUpdate(username="root2"),
    )
    assert cred.secret_enc == "enc:existing-passphrase"


def test_b1_same_key_type_explicit_retains_secret_enc(monkeypatch):
    """显式 PATCH 同型(type='key')且无 passphrase ⇒ 保留（须比 old_type，非仅看 type==key）。"""
    cred = SimpleNamespace(id=7, host_id=10, type="key", username="root",
                           secret_enc="enc:existing-passphrase", key_enc="enc:priv",
                           key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    asset_service.update_credential(
        FakeDb(), make_user(), 7, CredentialUpdate(type="key", username="root2"),
    )
    assert cred.secret_enc == "enc:existing-passphrase"


def test_b1_same_type_omitted_required_field_is_noop(monkeypatch):
    """同型无类型变更、必填字段缺省 ⇒ 不触发必填复核/清列（仅类型变更时复核）。"""
    cred = SimpleNamespace(id=7, host_id=10, type="key", username="root",
                           secret_enc=None, key_enc="enc:priv", key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    asset_service.update_credential(
        FakeDb(), make_user(), 7, CredentialUpdate(username="root2"),
    )
    assert cred.key_enc == "enc:priv"


# --------------------------------------------------- E. 型别切换清理/复核必填
def test_b1_type_switch_clears_other_column(monkeypatch):
    """key->password 切换须清 key_enc 并写入 secret_enc。"""
    cred = SimpleNamespace(id=7, host_id=10, type="key", username="root",
                           secret_enc=None, key_enc="enc:priv", key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    asset_service.update_credential(
        FakeDb(), make_user(), 7, CredentialUpdate(type="password", secret="newsecret"),
    )
    assert cred.type == "password"
    assert cred.key_enc is None, "stale key_enc must be cleared on type switch"
    assert cred.secret_enc and decrypt_secret(cred.secret_enc) == "newsecret"


def test_b1_type_switch_requires_new_type_secret(monkeypatch):
    """切换到 password 而无 secret -> 拒绝（对齐 create 必填口径）。"""
    cred = SimpleNamespace(id=7, host_id=10, type="key", username="root",
                           secret_enc=None, key_enc="enc:priv", key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    with pytest.raises(REJECT):
        asset_service.update_credential(
            FakeDb(), make_user(), 7, CredentialUpdate(type="password"),
        )


# ------------------------------------- F. 非法 type（create ∪ edit）拒绝
def test_b1_create_invalid_type_rejected(monkeypatch):
    """create 显式非法 type -> 400（契约终稿·create∪edit）。"""
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()), cred_repo=FakeCredRepo())
    with pytest.raises(BadRequestError):
        asset_service.create_credential(
            FakeDb(), make_user(),
            CredentialCreate(host_id=10, type="token", username="root", secret="s3cret"),
        )


def test_b1_update_invalid_type_rejected(monkeypatch):
    """update 显式非法 type -> 400（edit 同样成立）。"""
    cred = SimpleNamespace(id=7, host_id=10, type="password", username="root",
                           secret_enc="enc:secret", key_enc=None, key_version=1)
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(get=cred))
    with pytest.raises(BadRequestError):
        asset_service.update_credential(
            FakeDb(), make_user(), 7, CredentialUpdate(type="token"),
        )
