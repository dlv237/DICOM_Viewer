import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ImageViewer from './ImageViewer'
import { Activity } from 'lucide-react'

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
  const [openedDicom, setOpenedDicom] = useState<string | null>(null)

  const base = "http://localhost:8000"

  const navigate = useNavigate()

  useEffect(() => {
    const load = async () => {
      if (!id) return
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(`${base}/studies/${encodeURIComponent(id)}/dicoms`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        console.log(data)
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
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white shadow-sm border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-6 py-8">
          <div className="flex items-center gap-3 mb-2">
            <Activity className="h-8 w-8 text-blue-600" />
            <h1 className="text-3xl font-bold text-slate-800">DICOM Viewer</h1>
          </div>
        </div>
      </div>
      <div className="max-w-6xl mx-auto md:px-6">
        <div className='flex items-center justify-between mt-4'>
          <button
            className="mb-4 px-4 py-2 bg-slate-200 rounded hover:bg-slate-300"
            onClick={() => navigate(-1)}
          >
            Volver
          </button>
          <p className="text-slate-600 mb-6">StudyInstanceUID: {id}</p>
        </div>
        
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
                      <div className="mt-3 flex gap-3">
                        {it.Modality !== 'SR' && (
                          <button
                            className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
                            onClick={() => it.SOPInstanceUID && setOpenedDicom(`${base}/dicoms/${encodeURIComponent(it.SOPInstanceUID)}`)}
                          >
                            Ver DICOM
                          </button>
                        )}
                        <a
                          className="px-3 py-1 bg-slate-200 hover:bg-slate-300 rounded text-sm text-slate-800"
                          href={`${base}/dicoms/${encodeURIComponent(it.SOPInstanceUID)}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Descargar
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
  {openedDicom && <ImageViewer url={openedDicom} onClose={() => setOpenedDicom(null)} />}
    </div>
  )
}

export default StudyViewer
