// usaprais — tipos de los componentes de window.Prais (documentación).
import * as React from 'react';

export type Mood = 'tranqui' | 'pensando' | 'ganga' | 'pilas';
export type IconName = 'buscar' | 'flecha' | 'enlace' | 'check' | 'alerta' | 'envio' | 'escudo' | 'tienda' | 'compartir' | 'reloj' | 'volver' | 'imagen' | 'usuario' | 'chevron';
export type Canal = 'whatsapp' | 'x' | 'instagram';

/** Una oferta encontrada por Prais. */
export interface Oferta {
  tienda: string;
  /** Dónde se vende: "Instagram", "Mercado Libre", "Marketplace", "Tienda física", "Web"… */
  canal?: string;
  /** Precio del producto en dólares, sin envío. */
  usd: number;
  /** Envío en dólares. 0 = gratis, null/undefined = por confirmar. */
  envio?: number | null;
  condicion?: string;
  garantia?: string;
  ubicacion?: string;
  /** 0–5 */
  confianza?: number;
  /** Una línea en la voz de Prais. */
  nota?: string;
  href?: string;
  /** Ej.: "hace 3 días" */
  publicado?: string;
  /** URL de la foto del anuncio */
  foto?: string;
  vendedor?: { nombre?: string; tipo?: 'Particular' | 'Tienda'; desde?: number | string; referencias?: number };
  /** Si existe, la fila muestra "Ver ficha". */
  onAbrir?: () => void;
}

export interface WordmarkProps { size?: 'sm' | 'md' | 'lg' | 'xl'; dotcom?: boolean; className?: string; }
export interface PraisAvatarProps { mood?: Mood; size?: number; ground?: boolean; title?: string; className?: string; }
export interface PraisSaysProps { mood?: Mood; children: React.ReactNode; avatarSize?: number; nombre?: boolean; className?: string; }
export interface IconProps { name: IconName; size?: number; label?: string; className?: string; }
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> { variant?: 'primario' | 'secundario' | 'fantasma' | 'cartel'; size?: 'md' | 'lg'; icon?: IconName; iconRight?: IconName; }
export interface StickerProps { tone?: 'sol' | 'barato' | 'normal' | 'caro' | 'ojo'; tilt?: number; icon?: IconName; children: React.ReactNode; className?: string; }
export interface ChipProps { icon?: IconName; children: React.ReactNode; className?: string; }
export interface PriceTagProps { usd: number; tasa?: number; size?: 'sm' | 'md' | 'lg' | 'xl'; antes?: number; label?: string; align?: 'left' | 'right'; /** Bungee: solo capa de marca */ marca?: boolean; className?: string; }
export interface SearchBoxProps { onSubmit?: (valor: string) => void; label?: string; placeholder?: string; cta?: string; hint?: string; defaultValue?: string; className?: string; }
export interface PriceRangeProps { min: number; max: number; promedio: number; valor?: number; titulo?: string; etiquetaValor?: string; badge?: boolean; className?: string; }
export interface BadgeProps { tone?: 'destacado' | 'barato' | 'neutro' | 'caro'; icon?: IconName; children: React.ReactNode; className?: string; }
export interface EstadoPraisProps { tipo: 'cargando' | 'vacio' | 'error'; titulo?: string; texto?: string; mood?: Mood; size?: number; accion?: string; onAccion?: () => void; className?: string; }
export interface TrustDotsProps { value: number; }
export interface OfferRowProps extends Oferta { rank: number; tasa?: number; promedio?: number; destacado?: boolean; flag?: string; className?: string; }
export interface RankedListProps { ofertas: Oferta[]; tasa?: number; producto?: string; promedio?: number; actualizado?: string; className?: string; }
export interface MensajeCanalProps { canal: Canal; producto: string; ofertas: Oferta[]; tasa?: number; enlace?: string; promedio?: number; mood?: Mood; texto?: string; className?: string; }
export interface IGSlideProps { tipo: 'portada' | 'oferta' | 'cierre'; ancho?: number; producto?: string; revisados?: number; kicker?: string; oferta?: Oferta; rank?: number; de?: number; tasa?: number; ahorro?: number; titulo?: string; subtitulo?: string; className?: string; }

export interface FichaOfertaProps { oferta: Oferta; producto?: string; tasa?: number; rank?: number; de?: number; promedio?: number; revisiones?: { tono: 'ok' | 'ojo'; texto: string }[]; consejo?: React.ReactNode; mood?: Mood; mejor?: Oferta; masBaratas?: number; onVolver?: () => void; onIr?: () => void; onCompartir?: () => void; onVerMejor?: () => void; className?: string; }

export declare function Wordmark(p: WordmarkProps): JSX.Element;
export declare function PraisAvatar(p: PraisAvatarProps): JSX.Element;
export declare function PraisSays(p: PraisSaysProps): JSX.Element;
export declare function Icon(p: IconProps): JSX.Element;
export declare function Button(p: ButtonProps): JSX.Element;
export declare function Sticker(p: StickerProps): JSX.Element;
export declare function Chip(p: ChipProps): JSX.Element;
export declare function PriceTag(p: PriceTagProps): JSX.Element;
export declare function SearchBox(p: SearchBoxProps): JSX.Element;
export declare function PriceRange(p: PriceRangeProps): JSX.Element;
export declare function TrustDots(p: TrustDotsProps): JSX.Element;
export declare function OfferRow(p: OfferRowProps): JSX.Element;
export declare function RankedList(p: RankedListProps): JSX.Element;
export declare function MensajeCanal(p: MensajeCanalProps): JSX.Element;
export declare function IGSlide(p: IGSlideProps): JSX.Element;
export declare function FichaOferta(p: FichaOfertaProps): JSX.Element;
export declare function Badge(p: BadgeProps): JSX.Element;
export declare function EstadoPrais(p: EstadoPraisProps): JSX.Element;

/** Texto listo para enviar por el canal (WhatsApp con *negritas*, X ≤ 280 caracteres, DM de Instagram). */
export declare function textoParaCanal(canal: Canal, datos: { producto: string; ofertas: Oferta[]; tasa?: number; enlace?: string; promedio?: number }): string;
/** 'barato' ≤ 95% del promedio · 'normal' ≤ 105% · 'caro' por encima. */
export declare function veredicto(valor: number, promedio: number): 'barato' | 'normal' | 'caro';
export declare const formato: { usd(n: number): string; bs(n: number): string; num(n: number, decimales: number): string };
/** SVG de Prais como texto, para exportar o usar fuera de React. */
export declare function praisSVG(mood: Mood, paleta: Record<string, string>, opts?: { fondo?: boolean; title?: string; id?: string }): string;
