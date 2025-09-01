import React, { useEffect, useRef, useState } from 'react'
import * as cornerstone from "cornerstone-core";
import * as dicomParser from "dicom-parser";
// Suppress TS error: package has no type declarations
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
import cornerstoneWADOImageLoader from "cornerstone-wado-image-loader";


type Props = {
	url: string
	onClose: () => void
}

const ImageViewer: React.FC<Props> = ({ url, onClose }) => {
	const elementRef = useRef<HTMLDivElement | null>(null)
	const [diag, setDiag] = useState<string | null>(null)

  useEffect(() => {
    const el = elementRef.current;
    if (!el) return;

    cornerstoneWADOImageLoader.external.cornerstone = cornerstone;
    cornerstoneWADOImageLoader.external.dicomParser = dicomParser;
    cornerstoneWADOImageLoader.configure({ useWebWorkers: false });

    cornerstone.enable(el);

			(async () => {
			try {
				// Prefer fetching bytes and using dicomfile: scheme to avoid mis-parsing HTML/JSON
				const rawUrl = url.replace(/^wadouri:/, '');
				let imageId: string | undefined;
				try {
					const res = await fetch(rawUrl, {
						// Hint we want bytes
						headers: { Accept: 'application/dicom, application/octet-stream' },
					});
					if (res.ok) {
							const blob = await res.blob();
							// Parse a few tags to help diagnose issues
							try {
								const buf = await blob.arrayBuffer();
								const byteArray = new Uint8Array(buf);
								const data = dicomParser.parseDicom(byteArray, { untilTag: 'x7fe00010' });
								const ts = data.string('x00020010') || 'unknown';
								const sopClass = data.string('x00080016') || 'unknown';
								const rows = data.uint16('x00280010');
								const cols = data.uint16('x00280011');
								const hasPixel = !!(data.elements as any)['x7fe00010'];
								setDiag(`SOPClassUID=${sopClass}, TransferSyntaxUID=${ts}, Rows=${rows ?? '?'}, Cols=${cols ?? '?'}, PixelData=${hasPixel}`);
								if (!hasPixel) {
									throw new Error('El archivo DICOM no tiene PixelData (x7FE0,0010). No es una imagen renderizable.');
								}
							} catch (e) {
								// If parse fails, continue; loader may still handle it
							}
						// Name is not important for parsing
						const file = new File([blob], 'image.dcm', { type: 'application/dicom' });
						imageId = (cornerstoneWADOImageLoader as any).wadouri.fileManager.add(file);
					}
				} catch {
					// ignore fetch errors, will fallback to wadouri
				}

				if (!imageId) {
					// Fallback to direct wadouri
					imageId = url.startsWith('wadouri:') ? url : `wadouri:${url}`;
				}

						const image = await cornerstone.loadAndCacheImage(imageId);
						cornerstone.displayImage(el, image);
			} catch (err) {
				// eslint-disable-next-line no-console
						console.error('Error loading DICOM:', err);
						if (err instanceof Error) {
							setDiag((prev) => `${prev ? prev + ' | ' : ''}${err.message}`);
						}
			}
		})();

    return () => {
      try {
        cornerstone.disable(el);
      } catch {}
    };
  }, [url]);

	return (
		<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
			<div className="bg-white rounded-lg shadow-xl w-full max-w-5xl h-[80vh] flex flex-col">
				<div className="p-3 border-b flex items-center justify-between">
					<h3 className="font-semibold text-slate-800">Visor DICOM</h3>
					<button onClick={onClose} className="px-3 py-1 rounded bg-slate-200 hover:bg-slate-300 text-slate-800 text-sm">
						Cerrar
					</button>
				</div>
				{diag && (
					<div className="px-3 py-2 text-xs text-slate-700 bg-amber-50 border-b border-amber-200">
						{diag}
					</div>
				)}
				<div className="flex-1 bg-black">
					<div ref={elementRef} className="w-full h-full" style={{ width: '100%', height: '100%' }} />
				</div>
			</div>
		</div>
	)
}

export default ImageViewer

