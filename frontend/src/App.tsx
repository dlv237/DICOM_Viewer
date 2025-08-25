"use client"

import { useEffect, useState } from "react"
import { Search, Loader2, FileText, Activity } from "lucide-react"

type Study = { studyId: string; cleanReportText?: string }
type FindingValue = "Certainly True" | "Maybe True" | "Unknown" | "Maybe False" | "Certainly False"

function App() {
  const [studies, setStudies] = useState<Study[]>([])
  const [loading, setLoading] = useState(true)
  const [filtering, setFiltering] = useState(false)
  const [findings, setFindings] = useState<string[]>([])
  const [selectedFinding, setSelectedFinding] = useState<string>("")
  const [selectedValue, setSelectedValue] = useState<FindingValue>("Certainly True")

  useEffect(() => {
    const base = process.env.NODE_ENV === "development" ? "/api" : process.env.NEXT_PUBLIC_API_URL || "/api"
    const load = async () => {
      try {
        const [studiesRes, findingsRes] = await Promise.all([fetch(`${base}/studies`), fetch(`${base}/findings`)])
        const [studiesData, findingsData] = await Promise.all([studiesRes.json(), findingsRes.json()])
        setStudies(studiesData)
        setFindings(findingsData)
        if (findingsData.length && !selectedFinding) setSelectedFinding(findingsData[0])
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const onFilter = async () => {
    const base = process.env.NODE_ENV === "development" ? "/api" : process.env.NEXT_PUBLIC_API_URL || "/api"
    const params = new URLSearchParams()
    if (selectedFinding) params.set("hallazgo", selectedFinding)
    if (selectedValue) params.set("value", selectedValue)
    const url = `${base}/studies?${params.toString()}`
    console.log(url)
    setFiltering(true)
    try {
      const res = await fetch(url)
      const data: Study[] = await res.json()
      setStudies(data)
    } catch (e) {
      console.error(e)
    } finally {
      setFiltering(false)
    }
  }

  const getStatusColor = (value: FindingValue) => {
    switch (value) {
      case "Certainly True":
        return "text-emerald-600 bg-emerald-50"
      case "Maybe True":
        return "text-blue-600 bg-blue-50"
      case "Unknown":
        return "text-gray-600 bg-gray-50"
      case "Maybe False":
        return "text-orange-600 bg-orange-50"
      case "Certainly False":
        return "text-red-600 bg-red-50"
      default:
        return "text-gray-600 bg-gray-50"
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      <div className="bg-white shadow-sm border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-6 py-8">
          <div className="flex items-center gap-3 mb-2">
            <Activity className="h-8 w-8 text-blue-600" />
            <h1 className="text-3xl font-bold text-slate-800">DICOM Viewer</h1>
          </div>
          <p className="text-slate-600">Sistema de búsqueda y análisis de estudios médicos</p>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-8">
          <h2 className="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2">
            <Search className="h-5 w-5 text-blue-600" />
            Filtros de Búsqueda
          </h2>

          <div className="grid md:grid-cols-3 gap-4 items-end">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-700">Hallazgo Médico</label>
              <select
                value={selectedFinding}
                onChange={(e) => setSelectedFinding(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-slate-900"
                disabled={loading || filtering}
              >
                {findings.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-700">Valor de Certeza</label>
              <select
                value={selectedValue}
                onChange={(e) => setSelectedValue(e.target.value as FindingValue)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white text-slate-900"
                disabled={loading || filtering}
              >
                {(["Certainly True", "Maybe True", "Unknown", "Maybe False", "Certainly False"] as FindingValue[]).map(
                  (v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ),
                )}
              </select>
            </div>

            <button
              onClick={onFilter}
              disabled={loading || filtering}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-400 text-white font-medium rounded-lg transition-colors duration-200 flex items-center justify-center gap-2 h-10"
            >
              {filtering ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Buscando...
                </>
              ) : (
                <>
                  <Search className="h-4 w-4" />
                  Filtrar
                </>
              )}
            </button>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-slate-200">
          <div className="px-6 py-4 border-b border-slate-200">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
                <FileText className="h-5 w-5 text-blue-600" />
                Resultados de Estudios
              </h2>
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-600">Total encontrados:</span>
                <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium">
                  {studies.length}
                </span>
              </div>
            </div>
          </div>

          <div className="p-6">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <div className="text-center">
                  <Loader2 className="h-8 w-8 animate-spin text-blue-600 mx-auto mb-4" />
                  <p className="text-slate-600">Cargando estudios médicos...</p>
                </div>
              </div>
            ) : studies.length === 0 ? (
              <div className="text-center py-12">
                <FileText className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                <p className="text-slate-600">No se encontraron estudios con los filtros seleccionados</p>
              </div>
            ) : (
              <div className="space-y-4">
                {studies.map((s) => (
                  <div
                    key={s.studyId}
                    className="border border-slate-200 rounded-lg p-4 hover:shadow-md transition-shadow duration-200"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className="w-2 h-2 bg-blue-600 rounded-full"></div>
                        <h3 className="font-semibold text-slate-800">ID: {s.studyId}</h3>
                      </div>
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(selectedValue)}`}>
                        {selectedValue}
                      </span>
                    </div>
                    {s.cleanReportText && (
                      <div className="bg-slate-50 rounded-lg p-3">
                        <p className="text-sm text-slate-700 leading-relaxed">
                          {s.cleanReportText.slice(0, 200)}
                          {s.cleanReportText.length > 200 ? "..." : ""}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
