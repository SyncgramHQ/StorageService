import { useState } from "react";
import "./App.css";

const API_URL = (
  import.meta.env.VITE_API_URL || "https://imageserversyncgram.up.railway.app"
).replace(/\/$/, "");

const isPdfFilename = (filename) => filename?.toLowerCase().endsWith(".pdf");
const isImageFile = (file) => file?.type?.startsWith("image/");

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [accessUrl, setAccessUrl] = useState("");
  const [endpointUrl, setEndpointUrl] = useState("");
  const [uploadedFilename, setUploadedFilename] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      setSelectedFile(file);
      setError("");
      setAccessUrl("");
      setEndpointUrl("");
      setUploadedFilename("");
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file) {
      setSelectedFile(file);
      setError("");
      setAccessUrl("");
      setEndpointUrl("");
      setUploadedFilename("");

      // Update the file input to sync with drag & drop
      const fileInput = document.getElementById("fileInput");
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);
      fileInput.files = dataTransfer.files;
    } else {
      setError("Please drop a file");
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    setUploading(true);
    setError("");

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await fetch(`${API_URL}/upload`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (response.ok && data.success && data.filename) {
        const resolvedEndpointUrl =
          data.url || `${API_URL}/files/${encodeURIComponent(data.filename)}`;
        setUploadedFilename(data.filename);
        setEndpointUrl(resolvedEndpointUrl);
        setAccessUrl(resolvedEndpointUrl);
      } else {
        setError(data.error || "Upload failed");
      }
    } catch (err) {
      setError(err.message || "An error occurred during upload");
    } finally {
      setUploading(false);
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(accessUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      alert("Failed to copy URL");
    }
  };

  const handleUploadAnother = () => {
    setSelectedFile(null);
    setAccessUrl("");
    setEndpointUrl("");
    setUploadedFilename("");
    setError("");
    document.getElementById("fileInput").value = "";
  };

  const isPdf = isPdfFilename(uploadedFilename || selectedFile?.name);

  return (
    <div className="container">
      <h1>Image & File Hosting</h1>
      <p className="subtitle">
        Upload any file and get a temporary 10-minute access URL
      </p>

      <div className="upload-section">
        {!uploadedFilename ? (
          <>
            <form onSubmit={handleUpload}>
              <div
                className="file-input-wrapper"
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <input
                  type="file"
                  id="fileInput"
                  onChange={handleFileSelect}
                  required
                />
                <label
                  htmlFor="fileInput"
                  className={`${selectedFile ? "file-selected" : ""} ${isDragging ? "dragging" : ""}`}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="48"
                    height="48"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="17 8 12 3 7 8"></polyline>
                    <line x1="12" y1="3" x2="12" y2="15"></line>
                  </svg>
                  <span>
                    {isDragging
                      ? "Drop file here"
                      : selectedFile
                        ? selectedFile.name
                        : "Click or drag & drop a file"}
                  </span>
                </label>
              </div>
              <button type="submit" disabled={!selectedFile || uploading}>
                {uploading ? "Uploading..." : "Upload"}
              </button>
            </form>

            {uploading && (
              <div className="loading">
                <div className="spinner"></div>
                <p>Uploading...</p>
              </div>
            )}

            {error && (
              <div className="error">
                <p>{error}</p>
              </div>
            )}
          </>
        ) : (
          <div className="result">
            <div className="success-icon">✓</div>
            <h3>Upload Successful!</h3>
            <div className="url-box">
              <input
                type="text"
                value={accessUrl}
                readOnly
                placeholder="No access URL available"
              />
              <button
                onClick={handleCopy}
                className={copied ? "copied" : ""}
                disabled={!accessUrl}
              >
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>

            <div className="endpoint-note">
              <p>API file endpoint:</p>
              <code>{endpointUrl}</code>
            </div>

            {isPdf ? (
              <div className="preview preview-pdf">
                {accessUrl ? (
                  <a href={accessUrl} target="_blank" rel="noopener noreferrer">
                    Open PDF
                  </a>
                ) : (
                  <p>Temporary URL unavailable.</p>
                )}
              </div>
            ) : isImageFile(selectedFile) ? (
              <div className="preview">
                {accessUrl ? (
                  <img src={accessUrl} alt="Uploaded" />
                ) : (
                  <p>Temporary URL unavailable.</p>
                )}
              </div>
            ) : (
              <div className="preview preview-pdf">
                {accessUrl ? (
                  <a href={accessUrl} target="_blank" rel="noopener noreferrer">
                    Open File
                  </a>
                ) : (
                  <p>Temporary URL unavailable.</p>
                )}
              </div>
            )}
            <button onClick={handleUploadAnother} className="upload-another">
              Upload Another
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
