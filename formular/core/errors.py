"""Ошибки, которые можно показать пользователю без внутренних путей."""


class FormularError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status
