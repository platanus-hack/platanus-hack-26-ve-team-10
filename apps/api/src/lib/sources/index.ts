import type { Source } from "../types.js";
import { mockSource } from "./mock.js";

// Registro de fuentes. Para sumar una: crea sources/<fuente>.ts que exporte un Source
// (copia mock.ts como modelo) y agrégala a esta lista.
export const sources: Source[] = [mockSource];
