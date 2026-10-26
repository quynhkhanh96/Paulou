import { KeyboardEvent, ReactNode, useRef } from "react";

// WAI-ARIA tabs (automatic activation): arrow keys, Home and End move the
// selection. The caller renders the panel and wires it with `panelId` /
// `tabId`, so a panel can stay mounted (and keep its state) while hidden.

export interface TabItem {
  id: string;
  label: ReactNode;
}

export const tabId = (prefix: string, id: string) => `${prefix}-tab-${id}`;
export const panelId = (prefix: string, id: string) => `${prefix}-panel-${id}`;

interface Props {
  items: TabItem[];
  selected: string;
  onSelect: (id: string) => void;
  idPrefix: string;
  ariaLabel: string;
  variant?: "main" | "sub";
}

export function Tabs({ items, selected, onSelect, idPrefix, ariaLabel, variant = "sub" }: Props) {
  const refs = useRef(new Map<string, HTMLButtonElement>());

  const move = (event: KeyboardEvent, index: number) => {
    const last = items.length - 1;
    const next =
      event.key === "ArrowRight" ? (index === last ? 0 : index + 1)
      : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (next === null) return;
    event.preventDefault();
    const target = items[next].id;
    onSelect(target);
    refs.current.get(target)?.focus();
  };

  return (
    <div className={`tabs tabs-${variant}`} role="tablist" aria-label={ariaLabel}>
      {items.map((item, index) => {
        const active = item.id === selected;
        return (
          <button
            key={item.id}
            ref={(el) => {
              if (el) refs.current.set(item.id, el);
              else refs.current.delete(item.id);
            }}
            id={tabId(idPrefix, item.id)}
            type="button"
            role="tab"
            className={`tab ${active ? "is-active" : ""}`}
            aria-selected={active}
            aria-controls={panelId(idPrefix, item.id)}
            tabIndex={active ? 0 : -1}
            onClick={() => onSelect(item.id)}
            onKeyDown={(e) => move(e, index)}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
