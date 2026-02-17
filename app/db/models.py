import uuid
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Date,
    Time,
    Enum as SAEnum,
    Integer,
    Text,
    ForeignKey,
    Boolean,
    UniqueConstraint,
    Index,
    DECIMAL,
    Float,
    func,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class StatusAbsensi(PyEnum):
    TEPAT = "TEPAT"
    TERLAMBAT = "TERLAMBAT"


class RequestStatus(PyEnum):
    MENUNGGU = "MENUNGGU"
    SETUJU = "SETUJU"
    DITOLAK = "DITOLAK"


class JenisPengajuan(PyEnum):
    IZIN = "IZIN"
    SAKIT = "SAKIT"
    CUTI = "CUTI"


class KategoriAgenda(PyEnum):
    KERJA = "KERJA"
    MENGAJAR = "MENGAJAR"


# --- Models ---

class User(Base):
    __tablename__ = "users"

    id_user = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    status = Column(String(50), nullable=True)
    nomor_handphone = Column(String(20), nullable=True)
    nip = Column(String(50), unique=True, nullable=True)
    foto_profil_url = Column(Text, nullable=True)
    role = Column(String(50), default="GURU", nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # RBAC
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    overrides = relationship("UserPermissionOverride", back_populates="user", cascade="all, delete-orphan")

    # Auth
    reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")

    # Absensi & Shift
    jadwal_shift_kerjas = relationship("JadwalShiftKerja", back_populates="user", cascade="all, delete-orphan")
    absensis = relationship("Absensi", back_populates="user", cascade="all, delete-orphan")

    # Biometrics
    user_face = relationship("UserFace", back_populates="user", uselist=False, cascade="all, delete-orphan")

    # Face reset requests (pemohon vs admin)
    face_requests = relationship(
        "FaceResetRequest",
        foreign_keys="FaceResetRequest.id_user",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    admin_decisions = relationship(
        "FaceResetRequest",
        foreign_keys="FaceResetRequest.id_admin",
        back_populates="admin",
    )

    # Pengajuan absensi (pemohon vs admin)
    pengajuans = relationship(
        "PengajuanAbsensi",
        foreign_keys="PengajuanAbsensi.id_user",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    persetujuans_adm = relationship(
        "PengajuanAbsensi",
        foreign_keys="PengajuanAbsensi.id_admin",
        back_populates="admin",
    )

    # Agenda
    agendas = relationship("Agenda", back_populates="user", cascade="all, delete-orphan")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id_password_reset_token = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_user = Column(String(36), ForeignKey("users.id_user", ondelete="CASCADE"), nullable=False)
    code_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="reset_tokens")

    __table_args__ = (
        Index("idx_password_reset_tokens_user", "id_user"),
        Index("idx_password_reset_tokens_expires", "expires_at"),
    )


# ========== RBAC DINAMIS (CRUD) ==========

class Role(Base):
    __tablename__ = "roles"

    id_role = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"

    id_permission = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resource = Column(String(100), nullable=False)  # contoh: "absensi"
    action = Column(String(50), nullable=False)     # "create" | "read" | "update" | "delete"

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")
    user_overrides = relationship("UserPermissionOverride", back_populates="permission", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("resource", "action", name="uq_resource_action"),
        Index("idx_permissions_resource", "resource"),
        Index("idx_permissions_action", "action"),
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    id_user = Column(String(36), ForeignKey("users.id_user", ondelete="CASCADE"), primary_key=True)
    id_role = Column(String(36), ForeignKey("roles.id_role", ondelete="CASCADE"), primary_key=True)

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")

    __table_args__ = (Index("idx_user_roles_role", "id_role"),)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id_role = Column(String(36), ForeignKey("roles.id_role", ondelete="CASCADE"), primary_key=True)
    id_permission = Column(String(36), ForeignKey("permissions.id_permission", ondelete="CASCADE"), primary_key=True)

    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")

    __table_args__ = (Index("idx_role_permissions_permission", "id_permission"),)


class UserPermissionOverride(Base):
    __tablename__ = "user_permission_overrides"

    id_user = Column(String(36), ForeignKey("users.id_user", ondelete="CASCADE"), primary_key=True)
    id_permission = Column(String(36), ForeignKey("permissions.id_permission", ondelete="CASCADE"), primary_key=True)
    grant = Column(Boolean, nullable=False)  # true=allow, false=deny

    user = relationship("User", back_populates="overrides")
    permission = relationship("Permission", back_populates="user_overrides")

    __table_args__ = (Index("idx_user_perm_override_permission", "id_permission"),)


class PolaJamKerja(Base):
    __tablename__ = "pola_jam_kerja"

    id_pola_kerja = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nama_pola_kerja = Column(String(100), unique=True, nullable=False)
    jam_mulai_kerja = Column(Time, nullable=False)
    jam_selesai_kerja = Column(Time, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    jadwal_shifts = relationship("JadwalShiftKerja", back_populates="pola_jam_kerja", cascade="all, delete-orphan")


class JadwalShiftKerja(Base):
    __tablename__ = "jadwal_shift_kerja"

    id_jadwal_shift = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_user = Column(String(36), ForeignKey("users.id_user", ondelete="CASCADE"), nullable=False)
    id_pola_kerja = Column(String(36), ForeignKey("pola_jam_kerja.id_pola_kerja", ondelete="CASCADE"), nullable=False)
    tanggal = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="jadwal_shift_kerjas")
    pola_jam_kerja = relationship("PolaJamKerja", back_populates="jadwal_shifts")
    absensis = relationship("Absensi", back_populates="jadwal_shift_kerja")

    __table_args__ = (
        UniqueConstraint("id_user", "tanggal", name="uq_user_tanggal"),
        Index("idx_jadwal_tanggal", "tanggal"),
    )


class Lokasi(Base):
    __tablename__ = "lokasi"

    id_lokasi = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nama_lokasi = Column(String(100), unique=True, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    radius = Column(Integer, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relasi ganda ke Absensi (datang & pulang)
    absensis_datang = relationship(
        "Absensi",
        foreign_keys="Absensi.id_lokasi_datang",
        back_populates="lokasi_datang",
    )
    absensis_pulang = relationship(
        "Absensi",
        foreign_keys="Absensi.id_lokasi_pulang",
        back_populates="lokasi_pulang",
    )


class UserFace(Base):
    __tablename__ = "user_face"

    id_biometrik = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_user = Column(String(36), ForeignKey("users.id_user", ondelete="CASCADE"), unique=True, nullable=False)

    embedding_path = Column(Text, nullable=False)
    foto_referensi = Column(Text, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="user_face")


class Absensi(Base):
    __tablename__ = "absensi"

    id_absensi = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_user = Column(String(36), ForeignKey("users.id_user", ondelete="CASCADE"), nullable=False)
    id_jadwal_shift = Column(String(36), ForeignKey("jadwal_shift_kerja.id_jadwal_shift"), nullable=True)

    # Correlation ID untuk tracking/idempotency
    correlation_id = Column(String(36), unique=True, nullable=True)

    # FK Lokasi (Datang & Pulang)
    id_lokasi_datang = Column(String(36), ForeignKey("lokasi.id_lokasi"), nullable=True)
    id_lokasi_pulang = Column(String(36), ForeignKey("lokasi.id_lokasi"), nullable=True)

    waktu_masuk = Column(DateTime, server_default=func.now(), nullable=False)
    waktu_pulang = Column(DateTime, nullable=True)

    face_verified_masuk = Column(Boolean, default=False, nullable=False)
    face_verified_pulang = Column(Boolean, default=False, nullable=False)

    status_masuk = Column(SAEnum(StatusAbsensi, name="StatusAbsensi"), nullable=True)
    status_pulang = Column(SAEnum(StatusAbsensi, name="StatusAbsensi"), nullable=True)

    # Koordinat Aktual
    in_latitude = Column(DECIMAL(10, 6), nullable=True)
    in_longitude = Column(DECIMAL(10, 6), nullable=True)
    out_latitude = Column(DECIMAL(10, 6), nullable=True)
    out_longitude = Column(DECIMAL(10, 6), nullable=True)

    # Relationships
    user = relationship("User", back_populates="absensis")
    jadwal_shift_kerja = relationship("JadwalShiftKerja", back_populates="absensis")

    lokasi_datang = relationship("Lokasi", foreign_keys=[id_lokasi_datang], back_populates="absensis_datang")
    lokasi_pulang = relationship("Lokasi", foreign_keys=[id_lokasi_pulang], back_populates="absensis_pulang")

    __table_args__ = (
        Index("idx_absensi_user", "id_user"),
        Index("idx_absensi_waktu_masuk", "waktu_masuk"),
        Index("idx_absensi_correlation_id", "correlation_id"),
    )


class FaceResetRequest(Base):
    __tablename__ = "face_reset_requests"

    id_request = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_user = Column(String(36), ForeignKey("users.id_user", ondelete="CASCADE"), nullable=False)

    alasan = Column(Text, nullable=False)
    status = Column(SAEnum(RequestStatus, name="RequestStatus"), nullable=False, default=RequestStatus.MENUNGGU)

    admin_note = Column(Text, nullable=True)
    id_admin = Column(String(36), ForeignKey("users.id_user"), nullable=True)  # no ondelete di Prisma

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relasi ke User (pemohon)
    user = relationship("User", foreign_keys=[id_user], back_populates="face_requests")
    # Relasi ke User (admin pemroses)
    admin = relationship("User", foreign_keys=[id_admin], back_populates="admin_decisions")


class PengajuanAbsensi(Base):
    __tablename__ = "pengajuan_absensi"

    id_pengajuan = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_user = Column(String(36), ForeignKey("users.id_user", ondelete="CASCADE"), nullable=False)

    jenis_pengajuan = Column(SAEnum(JenisPengajuan, name="JenisPengajuan"), nullable=False)
    tanggal_mulai = Column(DateTime, nullable=False)
    tanggal_selesai = Column(DateTime, nullable=False)

    alasan = Column(Text, nullable=False)
    foto_bukti_url = Column(Text, nullable=True)

    status = Column(SAEnum(RequestStatus, name="RequestStatus"), nullable=False, default=RequestStatus.MENUNGGU)
    admin_note = Column(Text, nullable=True)

    id_admin = Column(String(36), ForeignKey("users.id_user"), nullable=True)  # no ondelete di Prisma

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", foreign_keys=[id_user], back_populates="pengajuans")
    admin = relationship("User", foreign_keys=[id_admin], back_populates="persetujuans_adm")


class Agenda(Base):
    __tablename__ = "agenda"

    id_agenda = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_user = Column(String(36), ForeignKey("users.id_user", ondelete="CASCADE"), nullable=False)

    kategori_agenda = Column(SAEnum(KategoriAgenda, name="KategoriAgenda"), nullable=False)
    deskripsi = Column(Text, nullable=False)

    tanggal = Column(Date, nullable=False)     # Prisma: @db.Date
    jam_mulai = Column(Time, nullable=False)   # Prisma: @db.Time
    jam_selesai = Column(Time, nullable=False) # Prisma: @db.Time

    bukti_pendukung_url = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="agendas")


class ProfileSekolah(Base):
    __tablename__ = "profile_sekolah"

    id_profile = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nama_sekolah = Column(String(255), nullable=False)
    no_telepon = Column(String(50), nullable=True)
    alamat_sekolah = Column(Text, nullable=False)
    npsn = Column(String(50), unique=True, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
