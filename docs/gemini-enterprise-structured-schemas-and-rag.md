# Gemini Enterprise: Structured Data Schemas, Document Parsing & RAG Chunking Guide

## 1. Overview & Authority
Gemini Enterprise (Discovery Engine / Vertex AI Search) supports structured data stores and unstructured documents with layout-aware parsing and chunking for Retrieval-Augmented Generation (RAG).

Reference endpoints:
- Schema management: `projects.locations.collections.dataStores.schemas`
- Serving config search: `projects.locations.collections.dataStores.servingConfigs:search`
- Document chunking: `projects.locations.collections.dataStores.branches.documents.chunks`

---

## 2. Structured Data Schemas

### Auto-Detection vs JSON Schema Specification
When importing structured data:
- **Auto-detect & edit**: Gemini Enterprise samples initial documents and proposes a schema. If `dynamic: "true"` (default), newly detected fields are added automatically.
- **Provide JSON Schema (`schemas.patch`)**: Supply a valid JSON Schema (draft 2020-12) defining property types and behaviors.
- **Backward Compatibility**: If a schema is updated, the new schema must be backward compatible with the original; otherwise, updates fail.

### JSON Schema Structure & Annotations
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "dynamic": "true",
  "datetime_detection": true,
  "geolocation_detection": true,
  "properties": {
    "title": {
      "type": "string",
      "keyPropertyMapping": "title",
      "retrievable": true,
      "completable": true
    },
    "description": {
      "type": "string",
      "keyPropertyMapping": "description"
    },
    "categories": {
      "type": "array",
      "items": {
        "type": "string",
        "keyPropertyMapping": "category"
      }
    },
    "uri": {
      "type": "string",
      "keyPropertyMapping": "uri"
    },
    "brand": {
      "type": "string",
      "indexable": true,
      "dynamicFacetable": true
    },
    "location": {
      "type": "geolocation",
      "indexable": true,
      "retrievable": true
    },
    "creationDate": {
      "type": "datetime",
      "indexable": true,
      "retrievable": true
    },
    "isCurrent": {
      "type": "boolean",
      "indexable": true,
      "retrievable": true
    }
  }
}
```

### Property Attributes & Limits
- **`keyPropertyMapping`**: Maps semantic keywords (`title`, `description`, `uri`, `category`). Auto-indexed and searchable by default.
- **`retrievable`**: Can be returned in search response (max 50 fields).
- **`indexable`**: Can be filtered, faceted, boosted, or sorted (max 50 fields).
- **`searchable`**: Reverse indexed for unstructured text queries (strings only, max 50 fields).
- **`dynamicFacetable`**: Usable as a dynamic facet (requires `indexable: true`).
- **`completable`**: Usable for autocomplete suggestions (strings only).

---

## 3. Document Parsers

Gemini Enterprise offers three parser engines:
1. **Layout Parser** (Default, Recommended):
   - Detects hierarchical structure (headings, paragraphs, lists, tables, images).
   - Supported on PDF, HTML, DOCX, PPTX, XLSX, XLSM.
   - Enables layout-aware chunking and table/image annotations.
   - HTML exclusion rules: `excludeHtmlElements`, `excludeHtmlClasses`, `excludeHtmlIds`.
2. **OCR Parser for PDFs**:
   - For scanned PDFs or PDFs with text inside images (up to 500 pages).
   - `useNativeText: true` merges digital machine-readable text with OCR output.
3. **Digital Parser**:
   - Fallback engine extracting raw machine-readable text blocks (used for TXT and basic text).

---

## 4. Chunk Documents for RAG

### Data Store Creation with Chunking
```json
{
  "displayName": "my_rag_datastore",
  "industryVertical": "GENERIC",
  "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
  "contentConfig": "CONTENT_REQUIRED",
  "documentProcessingConfig": {
    "chunkingConfig": {
      "layoutBasedChunkingConfig": {
        "chunkSize": 500,
        "includeAncestorHeadings": true
      }
    },
    "defaultParsingConfig": {
      "layoutParsingConfig": {}
    }
  }
}
```

### Search with Adjacent Chunks
```json
{
  "query": "query text",
  "pageSize": 5,
  "contentSearchSpec": {
    "searchResultMode": "CHUNKS",
    "chunkSpec": {
      "numPreviousChunks": 1,
      "numNextChunks": 1
    }
  }
}
```
Enables retrieving context before and after the matched chunk to preserve surrounding context for LLM generation.
