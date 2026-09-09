from __future__ import annotations


class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class DomainValidationError(DomainError):
    pass
