import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, apiBlob, qs } from "../api";
import { useAuth } from "../auth";
import { BadgeCartaPorte, ErrorMsg, Field, Modal, nullSiVacio, numOrNull } from "../components/ui";
import { capitalizar, fecha, num } from "../format";
import { useCampanias, useCampos } from "../hooks";
import type { CartaPorte, EstadoCartaPorte } from "../types";

const GRANOS = ["soja", "maíz", "trigo", "girasol", "sorgo", "cebada"];
const ESTADOS: EstadoCartaPorte[] = ["borrador", "emitida", "descargada", "anulada"];
const ACEPTA = ".pdf,.jpg,.jpeg,.png,.webp";

const VACIO = {
  estado: "borrador", numero_ctg: "", fecha_carga: new Date().toISOString().slice(0, 10), campania_id: "",
  campo_id: "", lote_id: "", grano: "soja", kilos_brutos: "", kilos_tara: "", kilos_netos: "", kilos_descargados: "",
  destino: "", destinatario_cuit: "", transportista_cuit: "", chofer_cuit: "", patente_camion: "",
  patente_acoplado: "", km_recorrer: "", observaciones: "",
};
type Form = Record<keyof typeof VACIO, string>;

const aForm = (cp: CartaPorte): Form =>
  Object.fromEntries(Object.keys(VACIO).map((k) => [k, cp[k as keyof CartaPorte] == null ? "" : String(cp[k as keyof CartaPorte])])) as Form;

function aPayload(f: Form) {
  const out: Record<string, unknown> = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, nullSiVacio(v)]));
  for (const k of ["campania_id", "campo_id", "lote_id", "km_recorrer"] as const) out[k] = numOrNull(f[k]);
  out.patente_camion = f.patente_camion.toUpperCase() || null;
  out.patente_acoplado = f.patente_acoplado.toUpperCase() || null;
  return out;
}

export default function CartasPorte() {
  const { puede } = useAuth();
  const campanias = useCampanias();
  const campos = useCampos();
  const [filtros, setFiltros] = useState({ campania_id: "", campo_id: "", grano: "", estado: "" });
  const [editando, setEditando] = useState<CartaPorte | "nueva" | null>(null);

  const lista = useQuery({
    queryKey: ["cartas-porte", filtros],
    queryFn: () => api<CartaPorte[]>(`/cartas-porte${qs({ ...filtros, limit: 200 })}`),
    refetchInterval: (q) => (q.state.data?.some((cp) => cp.estado === "procesando") ? 2500 : false),
  });
  const nombreCampo = (id: number | null) => campos.data?.find((c) => c.id === id)?.nombre ?? "—";
  const totalKilos = lista.data?.reduce((s, cp) => s + Number(cp.kilos_descargados ?? cp.kilos_netos ?? 0), 0) ?? 0;
  const set = (k: keyof typeof filtros) => (e: { target: { value: string } }) => setFiltros((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Cartas de porte</h1>
        {puede("cartas_porte:escribir") && (
          <div className="row">
            <ImportarCP />
            <button className="primary" onClick={() => setEditando("nueva")}>+ Nueva</button>
          </div>
        )}
      </div>
      <div className="row">
        <Field label="Campaña">
          <select value={filtros.campania_id} onChange={set("campania_id")}>
            <option value="">Todas</option>
            {campanias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select>
        </Field>
        <Field label="Campo">
          <select value={filtros.campo_id} onChange={set("campo_id")}>
            <option value="">Todos</option>
            {campos.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
          </select>
        </Field>
        <Field label="Grano">
          <select value={filtros.grano} onChange={set("grano")}>
            <option value="">Todos</option>
            {GRANOS.map((g) => <option key={g} value={g}>{capitalizar(g)}</option>)}
          </select>
        </Field>
        <Field label="Estado">
          <select value={filtros.estado} onChange={set("estado")}>
            <option value="">Todos</option>
            {ESTADOS.map((e) => <option key={e} value={e}>{capitalizar(e)}</option>)}
          </select>
        </Field>
      </div>

      <ErrorMsg error={lista.error} />
      <div className="card flush table-wrap">
        <table>
          <thead>
            <tr>
              <th>Fecha</th><th>CTG</th><th>Grano</th><th>Campo</th><th>Destino</th><th>Camión</th>
              <th className="num">Kg netos</th><th className="num">Kg descargados</th><th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {lista.data?.map((cp) => (
              <tr key={cp.id} className={cp.estado === "procesando" ? "" : "clickable"}
                onClick={() => cp.estado !== "procesando" && setEditando(cp)}>
                <td>{fecha(cp.fecha_carga)}</td>
                <td>{cp.numero_ctg ?? <span className="muted">—</span>}</td>
                <td>{cp.grano ? capitalizar(cp.grano) : "—"}</td>
                <td>{nombreCampo(cp.campo_id)}</td>
                <td>{cp.destino ?? "—"}</td>
                <td>{cp.patente_camion ?? "—"}</td>
                <td className="num">{num(cp.kilos_netos)}</td>
                <td className="num">{num(cp.kilos_descargados)}</td>
                <td>
                  <BadgeCartaPorte estado={cp.estado} />
                  {cp.error_extraccion && <span className="badge warning" title={cp.error_extraccion}> ! revisar</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {lista.isSuccess && !lista.data.length && <div className="empty">No hay cartas de porte cargadas.</div>}
      </div>
      {!!lista.data?.length && (
        <div className="muted">{lista.data.length} viajes · {num(totalKilos / 1000)} toneladas</div>
      )}

      {editando && (
        <FormCartaPorte cp={editando === "nueva" ? null : editando} soloLectura={!puede("cartas_porte:escribir")}
          onClose={() => setEditando(null)} />
      )}
    </div>
  );
}

function FormCartaPorte({ cp, soloLectura, onClose }: { cp: CartaPorte | null; soloLectura: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const campos = useCampos();
  const campanias = useCampanias();
  const [f, setF] = useState<Form>(cp ? aForm(cp) : VACIO);
  const lotes = campos.data?.find((c) => String(c.id) === f.campo_id)?.lotes ?? [];
  const set = (k: keyof Form) => (e: { target: { value: string } }) =>
    setF((p) => ({ ...p, [k]: e.target.value, ...(k === "campo_id" ? { lote_id: "" } : {}) }));

  const guardar = useMutation({
    mutationFn: () => api(cp ? `/cartas-porte/${cp.id}` : "/cartas-porte", { method: cp ? "PUT" : "POST", json: aPayload(f) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cartas-porte"] });
      qc.invalidateQueries({ queryKey: ["resumen"] });
      onClose();
    },
  });

  const netoCalculado = f.kilos_brutos && f.kilos_tara ? Number(f.kilos_brutos) - Number(f.kilos_tara) : null;

  return (
    <Modal titulo={cp ? `Carta de porte ${cp.numero_ctg ?? `#${cp.id}`}` : "Nueva carta de porte"} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); guardar.mutate(); }}>
        <fieldset disabled={soloLectura} style={{ border: "none", padding: 0, margin: 0 }}>
          <ErrorMsg error={guardar.error} />
          {cp?.error_extraccion && <div className="alert warning">{cp.error_extraccion}</div>}
          {cp?.archivo_id && <VerArchivo id={cp.id} />}
          <div className="form-grid" style={{ marginTop: 8 }}>
            <Field label="Fecha de carga"><input type="date" required value={f.fecha_carga} onChange={set("fecha_carga")} /></Field>
            <Field label="N° CTG"><input value={f.numero_ctg} onChange={set("numero_ctg")} /></Field>
            <Field label="Estado">
              <select value={f.estado} onChange={set("estado")}>
                {ESTADOS.map((e) => <option key={e} value={e}>{capitalizar(e)}</option>)}
              </select>
            </Field>
            <Field label="Grano">
              <select value={f.grano} onChange={set("grano")} required>
                <option value="">—</option>
                {[...new Set([...GRANOS, ...(f.grano ? [f.grano] : [])])].map((g) => <option key={g} value={g}>{capitalizar(g)}</option>)}
              </select>
            </Field>
            <Field label="Campaña">
              <select value={f.campania_id} onChange={set("campania_id")}>
                <option value="">—</option>
                {campanias.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
              </select>
            </Field>
            <Field label="Campo">
              <select value={f.campo_id} onChange={set("campo_id")}>
                <option value="">—</option>
                {campos.data?.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
              </select>
            </Field>
            <Field label="Lote">
              <select value={f.lote_id} onChange={set("lote_id")} disabled={!lotes.length}>
                <option value="">—</option>
                {lotes.map((l) => <option key={l.id} value={l.id}>{l.nombre}</option>)}
              </select>
            </Field>
            <Field label="Kg brutos"><input type="number" value={f.kilos_brutos} onChange={set("kilos_brutos")} /></Field>
            <Field label="Kg tara"><input type="number" value={f.kilos_tara} onChange={set("kilos_tara")} /></Field>
            <Field label="Kg netos">
              <input type="number" value={f.kilos_netos} onChange={set("kilos_netos")}
                placeholder={netoCalculado != null ? `${netoCalculado} (calculado)` : ""} />
            </Field>
            <Field label="Kg descargados"><input type="number" value={f.kilos_descargados} onChange={set("kilos_descargados")} /></Field>
            <Field label="Destino" wide><input value={f.destino} onChange={set("destino")} placeholder="Planta / puerto / acopio" /></Field>
            <Field label="CUIT destinatario"><input value={f.destinatario_cuit} onChange={set("destinatario_cuit")} /></Field>
            <Field label="CUIT transportista"><input value={f.transportista_cuit} onChange={set("transportista_cuit")} /></Field>
            <Field label="CUIT chofer"><input value={f.chofer_cuit} onChange={set("chofer_cuit")} /></Field>
            <Field label="Patente camión"><input value={f.patente_camion} onChange={set("patente_camion")} /></Field>
            <Field label="Patente acoplado"><input value={f.patente_acoplado} onChange={set("patente_acoplado")} /></Field>
            <Field label="Km a recorrer"><input type="number" value={f.km_recorrer} onChange={set("km_recorrer")} /></Field>
            <Field label="Observaciones" wide><textarea rows={2} value={f.observaciones} onChange={set("observaciones")} /></Field>
          </div>
        </fieldset>
        <div className="modal-actions">
          <button type="button" onClick={onClose}>{soloLectura ? "Cerrar" : "Cancelar"}</button>
          {!soloLectura && <button className="primary" disabled={guardar.isPending}>Guardar</button>}
        </div>
      </form>
    </Modal>
  );
}

/** Sube el PDF o una foto de una CPE: la lee Claude en el servidor y queda como borrador para revisar. */
function ImportarCP() {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const subir = useMutation({
    mutationFn: async (archivos: File[]) => {
      const errores: string[] = [];
      for (const a of archivos) {
        const fd = new FormData();
        fd.append("archivo", a);
        try {
          await api("/cartas-porte/importar", { method: "POST", body: fd });
        } catch (e) {
          errores.push(`${a.name}: ${e instanceof Error ? e.message : e}`);
        }
      }
      if (errores.length) throw new Error(errores.join(" · "));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["cartas-porte"] }),
  });
  return (
    <>
      <button onClick={() => input.current?.click()} disabled={subir.isPending}>
        {subir.isPending ? "Subiendo…" : "⬆ Importar PDF o foto"}
      </button>
      <input ref={input} type="file" accept={ACEPTA} multiple hidden
        onChange={(e) => { if (e.target.files?.length) subir.mutate(Array.from(e.target.files)); e.target.value = ""; }} />
      {subir.error && <ErrorMsg error={subir.error} />}
    </>
  );
}

function VerArchivo({ id }: { id: number }) {
  const [error, setError] = useState<unknown>(null);
  return (
    <div style={{ margin: "8px 0" }}>
      <button type="button" className="small" onClick={async () => {
        try {
          const blob = await apiBlob(`/cartas-porte/${id}/archivo`);
          window.open(URL.createObjectURL(blob), "_blank", "noopener");
        } catch (e) {
          setError(e);
        }
      }}>Ver el archivo original</button>
      <ErrorMsg error={error} />
    </div>
  );
}
