import { describe, expect, it } from "vitest";
import { comprobante, cuit, fecha, mes, monto, rangoMes } from "../format";

describe("formatos", () => {
  it("formatea CUIT con guiones", () => {
    expect(cuit("30712345678")).toBe("30-71234567-8");
    expect(cuit(null)).toBe("—");
  });

  it("arma el número de comprobante", () => {
    expect(comprobante({ tipo_comprobante: 1, punto_venta: 3, numero: 1542 })).toBe("Factura A 00003-00001542");
    expect(comprobante({ tipo_comprobante: 3, punto_venta: null, numero: null })).toBe("Nota de crédito A");
    expect(comprobante({ tipo_comprobante: 99, punto_venta: 1, numero: 2 })).toBe("Tipo 99 00001-00000002");
  });

  it("muestra fechas y meses en castellano", () => {
    expect(fecha("2026-10-05")).toBe("05/10/2026");
    expect(fecha(null)).toBe("—");
    expect(mes("2026-01")).toBe("ene 26");
    expect(mes(null)).toBe("Sin fecha");
  });

  it("calcula el rango de un mes (incluye años bisiestos)", () => {
    expect(rangoMes("2026-10")).toEqual({ desde: "2026-10-01", hasta: "2026-10-31" });
    expect(rangoMes("2028-02")).toEqual({ desde: "2028-02-01", hasta: "2028-02-29" });
  });

  it("muestra montos en dólares con prefijo", () => {
    expect(monto("100", "DOL")).toMatch(/^US\$ 100/);
    expect(monto(null, "PES")).toBe("—");
  });
});
