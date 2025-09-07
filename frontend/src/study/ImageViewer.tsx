import React, { useEffect, useRef, useState } from 'react'
import * as cornerstone from "cornerstone-core";
import * as dicomParser from "dicom-parser";
// @ts-ignore
import cornerstoneWADOImageLoader from "cornerstone-wado-image-loader";
// @ts-ignore
import dcmjs from "dcmjs";

type Props = {
  url: string
  onClose: () => void
}

const ImageViewer: React.FC<Props> = ({ url, onClose }) => {
  const elementRef = useRef<HTMLDivElement | null>(null)
  const [diag, setDiag] = useState<string | null>(null)
  const [srContent, setSrContent] = useState<any | null>(null)

  // ...existing code...
	useEffect(() => {
		const el = elementRef.current;
		if (!el) return;

		cornerstoneWADOImageLoader.external.cornerstone = cornerstone;
		cornerstoneWADOImageLoader.external.dicomParser = dicomParser;
		cornerstoneWADOImageLoader.configure({ useWebWorkers: false });

		cornerstone.enable(el);

		(async () => {
			try {
				const rawUrl = url.replace(/^wadouri:/, '');
				let blob: Blob | null = null;

				const res = await fetch(rawUrl, {
					headers: { Accept: 'application/dicom, application/octet-stream' },
				});
				if (res.ok) {
					blob = await res.blob();
				}
				if (!blob) throw new Error("No se pudo descargar el archivo DICOM");

				const buf = await blob.arrayBuffer();          // <- ArrayBuffer correcto
				const byteArray = new Uint8Array(buf);
				const data = dicomParser.parseDicom(byteArray, { untilTag: 'x7fe00010' });

				const ts = data.string('x00020010') || 'unknown';
				const sopClass = data.string('x00080016') || 'unknown';
				const modality = data.string('x00080060') || 'unknown';
				const hasPixel = !!(data.elements as any)['x7fe00010'];
				const isSR = modality === 'SR' || (sopClass?.startsWith('1.2.840.10008.5.1.4.1.1.88') ?? false);

				setDiag(`SOPClassUID=${sopClass}, TransferSyntaxUID=${ts}, Modality=${modality}, PixelData=${hasPixel}`);

				// SR: parsear con dcmjs desde ArrayBuffer
				if (isSR) {
					try {
						const dicomData = (dcmjs as any).data.DicomMessage.readFile(buf); // <- usar ArrayBuffer
						console.log(dicomData)
						const dataset = (dcmjs as any).data.DicomMetaDictionary.naturalizeDataset(dicomData.dict);
						// ContentSequence puede estar en varios niveles; normaliza a array
						const content = dataset.ContentSequence || dataset.Value || [];
						setSrContent(Array.isArray(content) ? content : [content]);
						return; // no intentar renderizar imagen
					} catch (e: any) {
						setDiag(prev => `${prev ? prev + ' | ' : ''}Error SR: ${e?.message || e}`);
						return; // evita caer en flujo de imagen
					}
				}

				// Imagen: usar fileManager
				if (hasPixel) {
					const file = new File([blob], 'image.dcm', { type: 'application/dicom' });
					const imageId = (cornerstoneWADOImageLoader as any).wadouri.fileManager.add(file);
					const image = await cornerstone.loadAndCacheImage(imageId);
					cornerstone.displayImage(el, image);
				} else {
					throw new Error("El archivo DICOM no contiene datos de imagen renderizable.");
				}
			} catch (err) {
				console.error("Error loading DICOM:", err);
				if (err instanceof Error) {
					setDiag((prev) => `${prev ? prev + ' | ' : ''}${err.message}`);
				}
			}
		})();

		return () => {
			try { cornerstone.disable(el); } catch {}
		};
	}, [url]);
// ...existing code...

  // Render de SR en lista simple
  const renderSR = (seq: any[]) => {
    return (
      <div className="p-3 overflow-auto text-sm text-slate-800">
        <h4 className="font-semibold mb-2">Structured Report</h4>
        <ul className="space-y-1">
          {seq.map((item, idx) => (
            <li key={idx} className="border-b border-slate-200 pb-1">
              <div><strong>{item.ConceptNameCodeSequence?.[0]?.CodeMeaning || "Item"}</strong></div>
              <div>{item.TextValue || item.NumericValue || JSON.stringify(item)}</div>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-5xl h-[80vh] flex flex-col">
        <div className="p-3 border-b flex items-center justify-between">
          <h3 className="font-semibold text-slate-800">Visor DICOM</h3>
          <button
            onClick={onClose}
            className="px-3 py-1 rounded bg-slate-200 hover:bg-slate-300 text-slate-800 text-sm"
          >
            Cerrar
          </button>
        </div>
        {diag && (
          <div className="px-3 py-2 text-xs text-slate-700 bg-amber-50 border-b border-amber-200">
            {diag}
          </div>
        )}
        <div className="flex-1 bg-black">
          {srContent ? (
            renderSR(srContent)
          ) : (
            <div ref={elementRef} className="w-full h-full" />
          )}
        </div>
      </div>
    </div>
  )
}

export default ImageViewer
