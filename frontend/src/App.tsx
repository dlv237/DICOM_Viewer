import { useEffect, useState } from 'react'

type Study = { id: number; name: string }

function App() {
  const [studies, setStudies] = useState<Study[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const base = import.meta.env.VITE_API_URL as string | undefined
        const url = base ? `${base}/studies` : '/api/studies'
        const res = await fetch(url)
        const data: Study[] = await res.json()
        setStudies(data)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return (
    <div style={{ fontFamily: 'system-ui', padding: 16 }}>
      <h1>DICOM Viewer</h1>
      {loading ? (
        <p>Cargando...</p>
      ) : (
        <ul>
          {studies.map((s) => (
            <li key={s.id}>{s.name}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default App
