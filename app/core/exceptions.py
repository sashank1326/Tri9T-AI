class MedicalQAException(Exception):
    """Base exception for Medical QA and Traceability System."""
    def __init__(self, message: str, status_code: int = 400, details: dict = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class DocumentNotFoundError(MedicalQAException):
    def __init__(self, document_id: str):
        super().__init__(f"Document '{document_id}' not found.", status_code=404)


class VersionNotFoundError(MedicalQAException):
    def __init__(self, document_id: str, version_id: str):
        super().__init__(
            f"Version '{version_id}' for document '{document_id}' not found.",
            status_code=404
        )


class NodeNotFoundError(MedicalQAException):
    def __init__(self, node_id: str):
        super().__init__(f"Document node '{node_id}' not found.", status_code=404)


class SelectionNotFoundError(MedicalQAException):
    def __init__(self, selection_id: str):
        super().__init__(f"Selection '{selection_id}' not found.", status_code=404)


class TestCaseNotFoundError(MedicalQAException):
    def __init__(self, test_case_id: str):
        super().__init__(f"Test case '{test_case_id}' not found.", status_code=404)


class GenerationNotFoundError(MedicalQAException):
    def __init__(self, generation_id: str):
        super().__init__(f"Generation batch '{generation_id}' not found.", status_code=404)


class DuplicateVersionError(MedicalQAException):
    def __init__(self, document_id: str, version_name: str):
        super().__init__(
            f"Version '{version_name}' already exists for document '{document_id}'.",
            status_code=409
        )


class PDFParseError(MedicalQAException):
    def __init__(self, message: str):
        super().__init__(f"PDF parsing error: {message}", status_code=422)


class LLMGenerationError(MedicalQAException):
    def __init__(self, message: str, details: dict = None):
        super().__init__(f"AI test-case generation failed: {message}", status_code=502, details=details)


class DatabaseConnectionError(MedicalQAException):
    def __init__(self, message: str):
        super().__init__(f"Database connection error: {message}", status_code=503)
