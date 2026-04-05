from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, quote, unquote, urlparse


@dataclass(frozen=True, slots=True)
class StoragePath:
    backend: str
    path: str
    connection_id: str = ""
    share_name: str = ""
    rclone_remote: str = ""

    @classmethod
    def local(cls, path: str | Path) -> "StoragePath":
        resolved = Path(path).expanduser().resolve()
        return cls(backend="local", path=str(resolved))

    @classmethod
    def smb(cls, *, connection_id: str, share_name: str, path: str = "/") -> "StoragePath":
        clean_connection_id = str(connection_id or "").strip()
        clean_share_name = str(share_name or "").strip().strip("/")
        normalized = cls._normalize_smb_path(path)
        if not clean_connection_id:
            raise ValueError("connection_id is required for smb storage paths")
        if not clean_share_name:
            raise ValueError("share_name is required for smb storage paths")
        return cls(backend="smb", path=normalized, connection_id=clean_connection_id, share_name=clean_share_name)

    @classmethod
    def rclone(cls, *, remote: str, path: str = "/") -> "StoragePath":
        clean_remote = str(remote or "").strip().strip("/")
        normalized = cls._normalize_rclone_path(path)
        if not clean_remote:
            raise ValueError("remote is required for rclone storage paths")
        return cls(backend="rclone", path=normalized, rclone_remote=clean_remote)

    @classmethod
    def from_uri(cls, value: str) -> "StoragePath":
        parsed = urlparse(str(value or ""))
        if parsed.scheme == "local":
            target = _decode_uri_component(parsed.path or "/")
            return cls.local(target)
        if parsed.scheme == "smb":
            params = parse_qs(parsed.query)
            connection_id = params.get("connection_id", [""])[0]
            share_name = _decode_uri_component(parsed.netloc or params.get("share_name", [""])[0])
            return cls.smb(
                connection_id=connection_id,
                share_name=share_name,
                path=_decode_uri_component(parsed.path or "/"),
            )
        if parsed.scheme == "rclone":
            params = parse_qs(parsed.query)
            remote = _decode_uri_component(parsed.netloc or params.get("remote", [""])[0])
            return cls.rclone(
                remote=remote,
                path=_decode_uri_component(parsed.path or "/"),
            )
        if value.startswith("/"):
            return cls.local(value)
        raise ValueError(f"unsupported storage uri: {value}")

    def to_uri(self) -> str:
        if self.backend == "local":
            return f"local://{quote(self.path)}"
        if self.backend == "smb":
            encoded_path = quote(self.normalized_path())
            encoded_connection = quote(self.connection_id)
            encoded_share = quote(self.share_name)
            return f"smb://{encoded_share}{encoded_path}?connection_id={encoded_connection}"
        if self.backend == "rclone":
            encoded_path = quote(self.normalized_path())
            encoded_remote = quote(self.rclone_remote)
            return f"rclone://{encoded_remote}{encoded_path}"
        raise ValueError(f"unsupported backend: {self.backend}")

    def normalized_path(self) -> str:
        if self.backend == "local":
            return str(Path(self.path).expanduser().resolve())
        if self.backend == "smb":
            return self._normalize_smb_path(self.path)
        if self.backend == "rclone":
            return self._normalize_rclone_path(self.path)
        raise ValueError(f"unsupported backend: {self.backend}")

    def name(self) -> str:
        if self.backend == "local":
            normalized = self.normalized_path()
            return Path(normalized).name or normalized
        if self.backend == "rclone":
            normalized = self.normalized_path()
            if normalized == "/":
                return self.rclone_remote or "/"
            return PurePosixPath(normalized).name
        normalized = self.normalized_path()
        if normalized == "/":
            return self.share_name or "/"
        return PurePosixPath(normalized).name

    def parent(self) -> "StoragePath | None":
        if self.backend == "local":
            current = Path(self.normalized_path())
            if current.parent == current:
                return None
            return StoragePath.local(current.parent)
        if self.backend == "rclone":
            current = PurePosixPath(self.normalized_path())
            if str(current) == "/":
                return None
            parent = str(current.parent)
            if not parent.startswith("/"):
                parent = f"/{parent}"
            return StoragePath.rclone(remote=self.rclone_remote, path=parent)
        current = PurePosixPath(self.normalized_path())
        if str(current) == "/":
            return None
        parent = str(current.parent)
        if not parent.startswith("/"):
            parent = f"/{parent}"
        return StoragePath.smb(connection_id=self.connection_id, share_name=self.share_name, path=parent)

    def join(self, *parts: str) -> "StoragePath":
        if self.backend == "local":
            base = Path(self.normalized_path())
            return StoragePath.local(base.joinpath(*parts))
        if self.backend == "rclone":
            base = PurePosixPath(self.normalized_path())
            clean_parts = [part.strip("/") for part in parts if str(part or "").strip("/")]
            joined = base.joinpath(*clean_parts)
            joined_text = str(joined)
            if not joined_text.startswith("/"):
                joined_text = f"/{joined_text}"
            return StoragePath.rclone(remote=self.rclone_remote, path=joined_text)
        base = PurePosixPath(self.normalized_path())
        clean_parts = [part.strip("/") for part in parts if str(part or "").strip("/")]
        joined = base.joinpath(*clean_parts)
        joined_text = str(joined)
        if not joined_text.startswith("/"):
            joined_text = f"/{joined_text}"
        return StoragePath.smb(connection_id=self.connection_id, share_name=self.share_name, path=joined_text)

    def with_name(self, name: str) -> "StoragePath":
        if self.backend == "local":
            return StoragePath.local(Path(self.normalized_path()).with_name(name))
        parent = self.parent()
        if parent is None:
            return self.join(name)
        return parent.join(name)

    def suffix(self) -> str:
        if self.backend == "local":
            return Path(self.normalized_path()).suffix.lower()
        if self.backend == "rclone":
            return PurePosixPath(self.normalized_path()).suffix.lower()
        return PurePosixPath(self.normalized_path()).suffix.lower()

    def relative_to(self, other: "StoragePath") -> str:
        if self.backend != other.backend:
            raise ValueError("storage backends do not match")
        if self.backend == "local":
            return str(Path(self.normalized_path()).relative_to(Path(other.normalized_path())))
        if self.backend == "rclone":
            if self.rclone_remote != other.rclone_remote:
                raise ValueError("rclone remotes do not match")
            return str(PurePosixPath(self.normalized_path()).relative_to(PurePosixPath(other.normalized_path())))
        if self.connection_id != other.connection_id or self.share_name != other.share_name:
            raise ValueError("smb roots do not match")
        return str(PurePosixPath(self.normalized_path()).relative_to(PurePosixPath(other.normalized_path())))
        raise ValueError(f"unsupported backend: {self.backend}")

    @staticmethod
    def _normalize_smb_path(value: str | Path) -> str:
        text = str(value or "").strip()
        if not text or text == ".":
            return "/"
        return "/" + text.strip("/")

    @staticmethod
    def _normalize_rclone_path(value: str | Path) -> str:
        text = str(value or "").strip()
        if not text or text == ".":
            return "/"
        return "/" + text.strip("/")


def _decode_uri_component(value: str) -> str:
    current = str(value or "")
    for _ in range(4):
        decoded = unquote(current)
        if decoded == current:
            break
        current = decoded
    return current
