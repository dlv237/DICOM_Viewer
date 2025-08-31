import React, { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'

type Item = {
  StudyInstanceUID?: string
  SeriesInstanceUID?: string
  SOPInstanceUID?: string
  PatientID?: string
  Modality?: string
  BodyPartExamined?: string | null
  AcquisitionDate?: string
  AcquisitionTime?: string
  file_path?: string
  dicom_path?: string
  path?: string
}

const StudyViewer: React.FC = () => {
  const { id } = useParams()
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const base = useMemo(() => (import.meta.env.DEV ? '/api' : import.meta.env.VITE_API_URL || '/api'), [])

  useEffect(() => {
    const load = async () => {
      if (!id) return
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(`${base}/studies/${encodeURIComponent(id)}/dicoms`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        setItems((data?.items as Item[]) || [])
      } catch (e: any) {
        setError(e?.message || 'Error')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [id, base])

  return (
    <div className="min-h-screen bg-slate-50 p-4 md:p-8">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-2xl font-bold mb-4">Study Viewer</h1>
        <p className="text-slate-600 mb-6">StudyInstanceUID: {id}</p>

        {loading && <div>Cargando imágenes...</div>}
        {error && <div className="text-red-600">{error}</div>}

        {!loading && !error && (
          <div className="space-y-4">
            {items.length === 0 ? (
              <div className="text-slate-600">No se encontraron DICOMs para este estudio.</div>
            ) : (
              <ul className="space-y-2">
                {items.map((it, idx) => (
                  <li key={it.SOPInstanceUID ?? idx} className="bg-white rounded-lg shadow border p-4">
                    <div className="text-sm text-slate-700">
                      <div><span className="font-medium">Modality:</span> {it.Modality || '-'}</div>
                      <div><span className="font-medium">Series:</span> {it.SeriesInstanceUID}</div>
                      <div><span className="font-medium">SOP:</span> {it.SOPInstanceUID}</div>
                      <div><span className="font-medium">Fecha/Hora:</span> {it.AcquisitionDate} {it.AcquisitionTime}</div>
                    </div>
                    {it.SOPInstanceUID && (
                      <div className="mt-2">
                        <a
                          className="text-blue-600 hover:underline"
                          href={`${base}/dicoms/${encodeURIComponent(it.SOPInstanceUID)}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Descargar DICOM
                        </a>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default StudyViewer
