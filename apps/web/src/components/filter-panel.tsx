"use client";
import { useRef, type ReactNode } from "react";
import { Icon } from "./icons";

export function FilterPanel({
  title,
  close,
  children,
}: {
  title: string;
  close: string;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  return (
    <div className="filter-panel">
      <div className="desktop-filter-content">{children}</div>
      <button
        className="button outline mobile-filter-trigger"
        onClick={() => dialog.current?.showModal()}
      >
        <Icon name="filter" />
        {title}
      </button>
      <dialog
        ref={dialog}
        className="filter-dialog"
        aria-label={title}
        onClick={(event) => {
          if (event.target === event.currentTarget) dialog.current?.close();
        }}
      >
        <div className="filter-dialog-heading">
          <h2>{title}</h2>
          <button
            className="button outline"
            onClick={() => dialog.current?.close()}
          >
            {close}
          </button>
        </div>
        {children}
      </dialog>
    </div>
  );
}
