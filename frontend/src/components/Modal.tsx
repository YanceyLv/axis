import { X } from "lucide-react";
import type { ReactNode } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  className?: string;
  headerExtra?: ReactNode;
  children: ReactNode;
}

export function Modal({ title, onClose, className = "", headerExtra, children }: ModalProps) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section className={`modal ${className}`} role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <header className="modal-header">
          <div className="modal-header-main">
            <h2 id="modal-title">{title}</h2>
          </div>
          {headerExtra ? <div className="modal-header-extra">{headerExtra}</div> : null}
          <button className="icon-button" type="button" aria-label="关闭" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
