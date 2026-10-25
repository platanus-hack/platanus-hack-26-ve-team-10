// Íconos del design system (docs/design-system/components/bundle.js): 24×24, trazo 2.25, puntas redondas.
const TRAZOS = {
  buscar: '<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5 L21 21"/>',
  flecha: '<path d="M4 12 H19 M13 6 L19 12 L13 18"/>',
  check: '<path d="M5 12.5 L10 17.5 L19 7"/>',
  alerta: '<path d="M12 3.5 L21.5 20 H2.5 Z"/><path d="M12 10 V14"/><path d="M12 17 V17.2"/>',
  escudo: '<path d="M12 3 L20 6 V12 C20 16.5 16.5 19.5 12 21 C7.5 19.5 4 16.5 4 12 V6 Z"/><path d="M8.5 12 L11 14.5 L15.5 9.5"/>',
  tienda: '<path d="M3.5 9 L5.5 4 H18.5 L20.5 9 Z"/><path d="M4.5 9 V20 H19.5 V9"/><path d="M9.5 20 V14.5 H14.5 V20"/>',
  reloj: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5 V12 L15 14"/>',
};

export function Icono({ nombre, size = 20, className }: { nombre: keyof typeof TRAZOS; size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`shrink-0 ${className ?? ""}`}
      dangerouslySetInnerHTML={{ __html: TRAZOS[nombre] }}
    />
  );
}
