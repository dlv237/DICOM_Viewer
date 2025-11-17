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

type StudyTextInfo = {
  studyId: string
  findings?: {
    study_date?: string | null
    age?: number | null
    report_text?: string | null
    regex_labels?: string | null
    llm_labels?: string | null
    label_status?: Record<string, string>
  } | null
  sections?: {
    projections?: string | null
    history?: string | null
    finding_sentences_es?: string | null
    finding_sentences_en?: string | null
  } | null
  sentences?: Array<{
    sentence_index?: number | null
    sentence_text?: string | null
    label?: string | null
    group?: string | null
  }>
}

const StudyViewer: React.FC = () => {
  const { id } = useParams()
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [openedDicom, setOpenedDicom] = useState<string | null>(null)
  const [textInfo, setTextInfo] = useState<StudyTextInfo | null>(null)

  const base = "http://localhost:8000"

  const navigate = useNavigate()

  useEffect(() => {
    const load = async () => {
      if (!id) return
      setLoading(true)
      setError(null)
      try {
        const [resDicoms, resText] = await Promise.all([
          fetch(`${base}/studies/${encodeURIComponent(id)}/dicoms`),
          fetch(`${base}/studies/${encodeURIComponent(id)}/text-info`),
        ])
        if (!resDicoms.ok) throw new Error(`HTTP ${resDicoms.status}`)
        const dicomData = await resDicoms.json()
        setItems((dicomData?.items as Item[]) || [])

        if (resText.ok) {
          const textData = (await resText.json()) as StudyTextInfo
          setTextInfo(textData)
        } else {
          setTextInfo(null)
        }
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
        
        {loading && <div>Cargando información...</div>}
        {error && <div className="text-red-600">{error}</div>}

        {!loading && !error && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Left: Text info */}
            <div className="space-y-4">
              <div className="bg-white rounded-lg shadow border p-4">
                <h3 className="text-lg font-semibold text-slate-800 mb-2">Reporte y Labels</h3>
                {!textInfo?.findings ? (
                  <p className="text-slate-600">No se encontró información de 100k_llm_findings_labels.csv.</p>
                ) : (
                  <div className="space-y-2 text-sm text-slate-800">
                    <div><span className="font-medium">Fecha estudio:</span> {textInfo.findings.study_date ?? '-'}</div>
                    <div><span className="font-medium">Edad:</span> {textInfo.findings.age ?? '-'}</div>
                    <div>
                      <span className="font-medium">Regex labels:</span>
                      <div className="mt-1 whitespace-pre-wrap break-words text-slate-700">{textInfo.findings.regex_labels || '-'}</div>
                    </div>
                    <div>
                      <span className="font-medium">LLM labels:</span>
                      <div className="mt-1 whitespace-pre-wrap break-words text-slate-700">{textInfo.findings.llm_labels || '-'}</div>
                    </div>
                    <div>
                      <span className="font-medium">Texto del reporte:</span>
                      <div className="mt-1 whitespace-pre-wrap break-words text-slate-700">{textInfo.findings.report_text || '-'}</div>
                    </div>
                    {textInfo.findings.label_status && Object.keys(textInfo.findings.label_status).length > 0 && (
                      <div>
                        <span className="font-medium">Estado de labels:</span>
                        <ul className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1">
                          {Object.entries(textInfo.findings.label_status).map(([k, v]) => (
                            <li key={k} className="text-slate-700"><span className="text-slate-500">{k}:</span> {String(v)}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="bg-white rounded-lg shadow border p-4">
                <h3 className="text-lg font-semibold text-slate-800 mb-2">Secciones del Reporte</h3>
                {!textInfo?.sections ? (
                  <p className="text-slate-600">No se encontró información de sections_of_report.csv.</p>
                ) : (
                  <div className="space-y-3 text-sm text-slate-800">
                    <div>
                      <span className="font-medium">Projections:</span>
                      <div className="mt-1 whitespace-pre-wrap break-words text-slate-700">{textInfo.sections.projections || '-'}</div>
                    </div>
                    <div>
                      <span className="font-medium">History:</span>
                      <div className="mt-1 whitespace-pre-wrap break-words text-slate-700">{textInfo.sections.history || '-'}</div>
                    </div>
                    <div>
                      <span className="font-medium">Finding sentences (ES):</span>
                      <div className="mt-1 whitespace-pre-wrap break-words text-slate-700">{textInfo.sections.finding_sentences_es || '-'}</div>
                    </div>
                    <div>
                      <span className="font-medium">Finding sentences (EN):</span>
                      <div className="mt-1 whitespace-pre-wrap break-words text-slate-700">{textInfo.sections.finding_sentences_en || '-'}</div>
                    </div>
                  </div>
                )}
              </div>

              <div className="bg-white rounded-lg shadow border p-4">
                <h3 className="text-lg font-semibold text-slate-800 mb-2">Oraciones Anotadas (5k)</h3>
                {!textInfo?.sentences || textInfo.sentences.length === 0 ? (
                  <p className="text-slate-600">No se encontraron oraciones en labels_per_sentence_5k.csv.</p>
                ) : (
                  <ul className="divide-y divide-slate-200">
                    {textInfo.sentences.map((s, i) => (
                      <li key={i} className="py-2 text-sm">
                        <div className="text-slate-500">Índice: {s.sentence_index ?? '-'}</div>
                        <div className="whitespace-pre-wrap break-words text-slate-800">{s.sentence_text || '-'}</div>
                        <div className="text-slate-700"><span className="text-slate-500">Label:</span> {s.label || '-'}</div>
                        <div className="text-slate-700"><span className="text-slate-500">Grupo:</span> {s.group || '-'}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            {/* Right: DICOMs */}
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
          </div>
        )}
      </div>
  {openedDicom && <ImageViewer url={openedDicom} onClose={() => setOpenedDicom(null)} />}
    </div>
  )
}

export default StudyViewer
