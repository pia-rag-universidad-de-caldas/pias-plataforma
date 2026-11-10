"""Data classes and interfaces of the project, grouped by function:

- entities: rows of the memory tables.
- schema, orm, files, repositories: the contract with the memory, by what each one is for (tables, the ORM adapter,
  the file adapter and what the domain sees of the memory).
- concepts: domain concepts that live in memory.
- results: what an `organize` operation returns.
- report: data of the statistics (GET /stats).
- queries: API queries (filters and pages).
- sources: where an ingestion reads from and the check of that source (feature 030).
- uploads: the files uploaded through the API and what each one became (feature 049).
- raw: the chunkable files published in data as RAW, and what a publication did (feature 042).
"""

from .concepts import (
    Category,
    DuplicateGroup,
    FileClassification,
    FileMetadata,
    Reason,
    RepeatedCode,
    RepeatedUpload,
    SourceFile,
)
from .entities import CategoryDefinition, FileCategory, FileRecord, IngestionRecord, Run, Upload
from .files import FileAdapter, FileError, FileInfo, FileReader, FileWriter
from .orm import Filter, MemoryStoreError, Operator, ORMAdapter, Row, SQLConverter
from .queries import FileFilter, FilePage
from .raw import RawFailure, RawFileRejected, RawPlan, RawPreview, RawStore, RawStoreError, RawSummary
from .report import (
    CleanupReport,
    DuplicateGroupReport,
    DuplicatesReport,
    EmptyFilesReport,
    NumericSummary,
    RepeatedCodeReport,
    RepeatedReport,
    RepeatedYearRow,
    ReportData,
    SmallFile,
    YearComparison,
    YearRow,
    YearsComparison,
)
from .repositories import CategoryRepository, FileRepository, RunRepository, UploadRepository
from .results import (
    CategoryChanges,
    DuplicatesSummary,
    FileFailure,
    IngestionOutcome,
    NewDuplicate,
    OrganizationPlan,
    Placement,
    Relocation,
    RunResult,
)
from .schema import ColumnSpec, DataType, Entity, ExistingColumn, TableSpec, Value
from .sources import IssueCode, IssueLevel, SourceCheck, SourceIssue, SourceKind, SourceUnavailable
from .uploads import IncomingFile, UploadResult, UploadState

__all__ = [
    "Category",
    "CategoryChanges",
    "CategoryDefinition",
    "CategoryRepository",
    "CleanupReport",
    "ColumnSpec",
    "DataType",
    "DuplicateGroup",
    "DuplicateGroupReport",
    "DuplicatesReport",
    "DuplicatesSummary",
    "EmptyFilesReport",
    "Entity",
    "ExistingColumn",
    "FileAdapter",
    "FileCategory",
    "FileClassification",
    "FileError",
    "FileFailure",
    "FileFilter",
    "FileInfo",
    "FileMetadata",
    "FilePage",
    "FileReader",
    "FileRecord",
    "FileRepository",
    "FileWriter",
    "Filter",
    "IncomingFile",
    "IngestionOutcome",
    "IngestionRecord",
    "IssueCode",
    "IssueLevel",
    "MemoryStoreError",
    "NewDuplicate",
    "NumericSummary",
    "ORMAdapter",
    "Operator",
    "OrganizationPlan",
    "Placement",
    "RawFailure",
    "RawFileRejected",
    "RawPlan",
    "RawPreview",
    "RawStore",
    "RawStoreError",
    "RawSummary",
    "Reason",
    "Relocation",
    "RepeatedCode",
    "RepeatedCodeReport",
    "RepeatedReport",
    "RepeatedUpload",
    "RepeatedYearRow",
    "ReportData",
    "Row",
    "Run",
    "RunRepository",
    "RunResult",
    "SQLConverter",
    "SmallFile",
    "SourceCheck",
    "SourceFile",
    "SourceIssue",
    "SourceKind",
    "SourceUnavailable",
    "TableSpec",
    "Upload",
    "UploadRepository",
    "UploadResult",
    "UploadState",
    "Value",
    "YearComparison",
    "YearRow",
    "YearsComparison",
]
