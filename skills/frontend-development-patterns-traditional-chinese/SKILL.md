---
name: frontend-development-patterns-traditional-chinese
description: Modern frontend architecture, React 19, Next.js App Router, TypeScript conventions, state management boundaries, and performance optimization patterns documented natively in Traditional Chinese (繁體中文).
version: 1.0.0
---

# 🎨 前端架構與現代開發模式 (Frontend Development Patterns — 繁體中文版)

`frontend-development-patterns-traditional-chinese` 是 NouGenShards 吸收的前端架構核心指引，為全艦隊（Antigravity、Kaedra、Rhea-Noir 等）提供現代前端工程、React、Next.js App Router、TypeScript、元件組合、狀態邊界以及渲染效能的最佳實踐標準。

---

## 🏛️ 1. 核心架構原則 (Core Architectural Principles)

### 1.1 單向數據流與職責分離 (Unidirectional Data Flow & Separation of Concerns)
- **Container / Presenter 分離**：
  - **容器組件 (Container Components)**：負責獲取數據、處理商業邏輯、訂閱 store 或調用 Server Actions，不負責過多的 CSS 排版。
  - **展示組件 (Presentational Components)**：純粹接收 props 並呈現 UI，無副作用，易於單元測試與 Storybook 預覽。
- **組件組合 (Composition over Inheritance)**：
  - 優先使用 `children`、Compound Components（複合組件模式）或 Render Props，避免深層的 Props Drilling。

### 1.2 嚴格的 Server 與 Client 邊界 (Next.js App Router RSC Rules)
- **預設為 Server Components (RSC)**：
  - 預設所有頁面與組件均在伺服器端渲染，享有零客戶端 Bundle 成本、直接存取資料庫與秘密金鑰的優勢。
- **最小化 `'use client'` 作用域**：
  - 僅在需要瀏覽器 API（如 `window`, `localStorage`）、事件監聽器（`onClick`, `onChange`）或 React Hooks（`useState`, `useEffect`）時，將 `'use client'` 下推至最底層的葉子節點（Leaf Components）。
  - 不要將整個 Page 或整個 Layout 標記為 `'use client'`。

---

## ⚡ 2. 狀態管理邊界 (State Management Boundaries)

| 狀態類型 | 推薦解決方案 | 適用情境 |
|---|---|---|
| **URL 狀態** | `searchParams`, `nuqs`, Next.js 路由 | 篩選條件、分頁、排序、Tab 切換（具備可分享與書籤特性） |
| **伺服器緩存狀態** | TanStack Query (React Query) / SWR / RSC | API 查詢、自動重新整理、樂觀更新 (Optimistic Updates) |
| **全域客戶端狀態** | Zustand | 使用者偏好、購物車、跨頁面暫存狀態（輕量且無 Context 重繪問題） |
| **局部組件狀態** | `useState`, `useReducer` | 表單輸入、Dropdown 開關、Modal 顯示狀態 |

### 2.1 避免常見的狀態反模式 (Anti-patterns)
- ❌ **禁止將 Props 鏡像到 State**：若非為了初始化獨立草稿，切勿 `const [val, setVal] = useState(props.val)`，否則 Props 更新時狀態不會同步。
- ❌ **禁止過度使用 `useEffect` 進行數據轉換**：衍生數據（Derived State）應直接在渲染過程中透過 `useMemo` 或純運算得出，避免連鎖觸發多次 Render。

---

## 🧩 3. TypeScript 與型別設計模式 (Type Engineering)

### 3.1 嚴格型別定義與 Discriminated Unions
```tsx
// ✅ 推薦：可辨識聯合型別 (Discriminated Union) 處理非同步狀態
type AsyncData<T> =
  | { status: 'idle'; data: null; error: null }
  | { status: 'loading'; data: null; error: null }
  | { status: 'success'; data: T; error: null }
  | { status: 'error'; data: null; error: Error };

// ✅ 推薦：嚴格且具擴展性的組件 Props
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
}
```

### 3.2 避免使用 `any` 與非空斷言 (`!`)
- 使用 `unknown` 代替 `any`，並透過 Type Guard（型別守衛）或 Zod 進行 Runtime Schema 驗證。

---

## 🚀 4. 效能優化準則 (Performance Optimization)

1. **渲染效能優化 (Render Optimization)**：
   - 謹慎使用 `useMemo` 與 `useCallback`：僅在傳遞給經 `React.memo` 包裹的子組件、或昂貴計算（如千項數組排序/過濾）時使用。
   - 列表渲染必須提供穩定且唯一的 `key`（禁止使用 array index 作為動態增刪項目的 key）。
2. **資源延遲載入 (Code Splitting & Lazy Loading)**：
   - 大型第三方庫（如圖表庫、富文本編輯器）或重型 Modal 彈窗，使用 `React.lazy` 或 Next.js `dynamic(() => import(...), { ssr: false })` 動態載入。
3. **Core Web Vitals (LCP, CLS, INP)**：
   - **圖片優化**：強制使用 Next.js `<Image />`，指定 `width`/`height` 防止佈局位移 (CLS)，重要首屏圖片標記 `priority`。
   - **字體載入**：使用 `next/font` 進行字體子集化與零佈局偏移載入。

---

## ♿ 5. 無障礙與設計規範 (Accessibility & Styling Standards)

- **語意化 HTML**：優先使用原生標籤（`<header>`, `<nav>`, `<main>`, `<article>`, `<button>`），而非全部使用 `<div>`。
- **無障礙 (a11y) 屬性**：
  - 只有圖示的按鈕必須提供 `aria-label`。
  - 表單輸入項必須與 `<label htmlFor="...">` 關聯。
  - 支援全鍵盤導航（`:focus-visible` 樣式完整、Tab 順序合理）。
- **樣式約定 (Tailwind CSS / CSS Modules)**：
  - 遵循一致的色彩變數、間距階梯與深色模式支援。
  - 使用 `clsx` 或 `tailwind-merge` (`cn(...)`) 合併條件類名。

---

## 📋 6. 現代前端代碼審查檢查清單 (Code Review Checklist)

- [ ] 是否將不必要的 `'use client'` 移除，讓組件留在 Server 端？
- [ ] 所有非同步操作是否有明確的 Loading 與 Error 狀態處理？
- [ ] 是否杜絕了重複請求（使用 SWR / TanStack Query 快取機制）？
- [ ] 圖片與動態資源是否指定尺寸防止 CLS？
- [ ] 所有輸入與 API 邊界是否有 Zod 或嚴格型別校驗？
- [ ] 鍵盤焦點與無障礙標籤 (ARIA) 是否具備？
