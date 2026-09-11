---
name: motion-patterns
description: Production-ready component animation patterns, transition tokens, gesture feedback, layout morphing, exit choreography with AnimatePresence, and SSR/reduced-motion safe motion engineering for React 19 and Next.js (motion/react / Framer Motion).
version: 1.0.0
---

# 🎭 Motion Patterns (NouGen Shang Tsung Edition)

`motion-patterns` is the production motion engineering standard for the NouGen fleet. It provides verified animation patterns for modern React (React 19) and Next.js App Router applications using `motion/react` (the official modular package of Framer Motion). It unifies spring physics, micro-interactions, layout transitions, exit choreography, and accessibility into a deterministic playbook.

---

## 🏛️ 1. Core Principles & Motion Tokens

### 1.1 Physics-Based Spring Constants
Avoid hardcoded linear durations where organic feel is desired. Standardize on three primary spring archetypes:

```typescript
export const SPRING_TOKENS = {
  // Snappy: Buttons, toggles, micro-interactions, tooltips
  snappy: { type: "spring", stiffness: 500, damping: 30, mass: 0.5 },
  // Standard: Dropdowns, dialogs, drawers, bottom sheets
  smooth: { type: "spring", stiffness: 350, damping: 25, mass: 1 },
  // Gentle: Page transitions, layout morphing, heavy cards
  gentle: { type: "spring", stiffness: 200, damping: 20, mass: 1.2 },
} as const;
```

### 1.2 Hardware Acceleration & GPU Constraints
- **Only animate composite properties**: `transform` (`scale`, `x`, `y`, `rotate`) and `opacity`.
- **Never animate layout trigger properties**: Avoid animating `width`, `height`, `top`, `left`, `margin`, or `padding` directly. Use `layout` or `layoutId` for smooth geometric transitions.
- **Set `will-change` conservatively**: Let `motion` manage layer promotion dynamically, or apply `will-change: transform, opacity` only during active interaction states.

### 1.3 Accessibility (`prefers-reduced-motion`)
Always respect user preferences. Wrap motion components or configure global motion features:

```tsx
import { useReducedMotion } from "motion/react";

export function useMotionPreference() {
  const shouldReduceMotion = useReducedMotion();
  return {
    shouldReduceMotion,
    getTransition: (standard: object) =>
      shouldReduceMotion ? { duration: 0.01 } : standard,
  };
}
```

---

## ⚡ 2. Canonical UI Component Patterns

### 2.1 Micro-Interactive Buttons & Action Targets
```tsx
import { motion } from "motion/react";
import { SPRING_TOKENS } from "./tokens";

export function MotionButton({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <motion.button
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.96 }}
      transition={SPRING_TOKENS.snappy}
      onClick={onClick}
      className="px-4 py-2 rounded-lg bg-primary text-primary-foreground font-medium"
    >
      {children}
    </motion.button>
  );
}
```

### 2.2 Modal & Backdrop Exit Choreography (`AnimatePresence`)
```tsx
import { motion, AnimatePresence } from "motion/react";
import { SPRING_TOKENS } from "./tokens";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
}

export function MotionModal({ isOpen, onClose, children }: ModalProps) {
  return (
    <AnimatePresence mode="wait">
      {isOpen && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
          />
          <motion.div
            key="content"
            initial={{ opacity: 0, scale: 0.95, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 12 }}
            transition={SPRING_TOKENS.smooth}
            className="fixed inset-0 m-auto max-w-lg h-fit p-6 bg-card rounded-2xl shadow-2xl z-50"
          >
            {children}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
```

### 2.3 Staggered Lists & Feed Entrances
```tsx
import { motion } from "motion/react";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.06,
      delayChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 14 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: "spring", stiffness: 350, damping: 25 },
  },
};

export function MotionList<T>({ items, renderItem }: { items: T[]; renderItem: (item: T) => React.ReactNode }) {
  return (
    <motion.ul variants={containerVariants} initial="hidden" animate="visible" className="space-y-2">
      {items.map((item, idx) => (
        <motion.li key={idx} variants={itemVariants}>
          {renderItem(item)}
        </motion.li>
      ))}
    </motion.ul>
  );
}
```

### 2.4 Shared Element Layout Morphing (`layoutId`)
```tsx
import { useState } from "react";
import { motion } from "motion/react";

export function SegmentedTabs({ tabs }: { tabs: string[] }) {
  const [activeTab, setActiveTab] = useState(tabs[0]);

  return (
    <div className="flex bg-muted p-1 rounded-xl gap-1">
      {tabs.map((tab) => {
        const isActive = activeTab === tab;
        return (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="relative px-4 py-1.5 text-sm font-medium rounded-lg transition-colors"
          >
            {isActive && (
              <motion.div
                layoutId="active-tab-indicator"
                className="absolute inset-0 bg-background rounded-lg shadow-sm"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
            )}
            <span className="relative z-10">{tab}</span>
          </button>
        );
      })}
    </div>
  );
}
```

---

## 🛠️ 3. Next.js App Router SSR Safety

1. **Client Boundary**: Any component importing from `motion/react` must reside in a file marked `'use client'`.
2. **Eliminate Hydration Mismatches**: Do not calculate window dimensions or conditional initial transforms based on browser viewport before mount. Use `initial={false}` on initial page load if mounting elements with SSR state.
3. **Lazy Motion Loading**: For bundle optimization on high-traffic sites, utilize `LazyMotion` and `domAnimation` from `motion/react` to reduce JavaScript bundle footprint by ~70%:
   ```tsx
   import { LazyMotion, domAnimation, m } from "motion/react";

   export function MotionBoundary({ children }: { children: React.ReactNode }) {
     return (
       <LazyMotion features={domAnimation} strict>
         {children}
       </LazyMotion>
     );
   }
   ```

---

## 📋 4. Motion Quality & Code Review Checklist

- [ ] Does every interactive animation respect `prefers-reduced-motion`?
- [ ] Are animations restricted to composite properties (`transform`, `opacity`) without triggering layout reflow?
- [ ] Is `AnimatePresence` configured with `mode="wait"` or unique `key` attributes on children?
- [ ] Are `'use client'` boundaries isolated to leaf UI components rather than server-rendered layouts?
- [ ] Do shared-element animations use unique, collision-free `layoutId` keys?
