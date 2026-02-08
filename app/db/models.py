import uuid
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, String, DateTime, Time, Enum, Integer, Text, ForeignKey,
    Boolean, UniqueConstraint, Index, DECIMAL, Float, func
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

# --- Enums ---

class StatusAbsensi(PyEnum):
    TEPAT = "TEPAT"
    TERLAMBAT = "TERLAMBAT"

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
    role = Column(String(50), default="GURU")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    overrides = relationship("UserPermissionOverride", back_populates="user", cascade="all, delete-orphan")
    reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")
    jadwal_shift_kerjas = relationship("JadwalShiftKerja", back_populates="user", cascade="all, delete-orphan")
    user_face = relationship("UserFace", back_populates="user", uselist=False, cascade="all, delete-orphan")
    absensis = relationship("Absensi", back_populates="user", cascade="all, delete-orphan")


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


class Role(Base):
    __tablename__ = "roles"

    id_role = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"

    id_permission = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resource = Column(String(100), nullable=False)  # contoh: "absensi"
    action = Column(String(50), nullable=False)    # "create", "read", dll
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

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
    grant = Column(Boolean, nullable=False) # true=allow, false=deny

    user = relationship("User", back_populates="overrides")
    permission = relationship("Permission", back_populates="user_overrides")

    __table_args__ = (Index("idx_user_perm_override_permission", "id_permission"),)


class PolaJamKerja(Base):
    __tablename__ = "pola_jam_kerja"

    id_pola_kerja = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nama_pola_kerja = Column(String(100), unique=True, nullable=False)
    jam_mulai_kerja = Column(Time, nullable=False)
    jam_selesai_kerja = Column(Time, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    jadwal_shifts = relationship("JadwalShiftKerja", back_populates="pola_jam_kerja")


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
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Menangani relasi ganda ke tabel Absensi
    absensis_datang = relationship("Absensi", foreign_keys="[Absensi.id_lokasi_datang]", back_populates="lokasi_datang")
    absensis_pulang = relationship("Absensi", foreign_keys="[Absensi.id_lokasi_pulang]", back_populates="lokasi_pulang")


class UserFace(Base):
    __tablename__ = "user_face"

    id_biometrik = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_user = Column(String(36), ForeignKey("users.id_user", ondelete="CASCADE"), unique=True, nullable=False)
    embedding_path = Column(Text, nullable=False)
    foto_referensi = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="user_face")


class Absensi(Base):
    __tablename__ = "absensi"

    id_absensi = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_user = Column(String(36), ForeignKey("users.id_user", ondelete="CASCADE"), nullable=False)
    id_jadwal_shift = Column(String(36), ForeignKey("jadwal_shift_kerja.id_jadwal_shift"), nullable=True)

    correlation_id = Column(String(36), unique=True, index=True, nullable=True)
    
    # Foreign Keys untuk Lokasi (Datang & Pulang)
    id_lokasi_datang = Column(String(36), ForeignKey("lokasi.id_lokasi"), nullable=True)
    id_lokasi_pulang = Column(String(36), ForeignKey("lokasi.id_lokasi"), nullable=True)

    waktu_masuk = Column(DateTime, server_default=func.now())
    waktu_pulang = Column(DateTime, nullable=True)

    face_verified_masuk = Column(Boolean, default=False)
    face_verified_pulang = Column(Boolean, default=False)

    status_masuk = Column(Enum(StatusAbsensi), nullable=True)
    status_pulang = Column(Enum(StatusAbsensi), nullable=True)

    in_latitude = Column(DECIMAL(10, 6), nullable=True)
    in_longitude = Column(DECIMAL(10, 6), nullable=True)
    out_latitude = Column(DECIMAL(10, 6), nullable=True)
    out_longitude = Column(DECIMAL(10, 6), nullable=True)

    # Relationships
    user = relationship("User", back_populates="absensis")
    jadwal_shift_kerja = relationship("JadwalShiftKerja", back_populates="absensis")
    
    # Menghubungkan ke Lokasi secara spesifik menggunakan foreign_keys
    lokasi_datang = relationship("Lokasi", foreign_keys=[id_lokasi_datang], back_populates="absensis_datang")
    lokasi_pulang = relationship("Lokasi", foreign_keys=[id_lokasi_pulang], back_populates="absensis_pulang")

    __table_args__ = (
        Index("idx_absensi_user", "id_user"),
        Index("idx_absensi_waktu_masuk", "waktu_masuk"),
    )