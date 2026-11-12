"""
Create a dummy 'client_downloads' folder with mixed files for testing the sorter.
The files are empty placeholders - no real client data.

Usage:
    python make_test_folder.py            # creates ./client_downloads
"""

from pathlib import Path

FILES = [
    "scan001.pdf", "scan002.PDF", "High_Court_Filing_Kamau_v_Otieno.pdf",
    "IMG_4827.jpg", "IMG_4828.JPG", "evidence_photo_gate.jpeg", "Screenshot_whatsapp.png",
    "Contract_FINAL_v3.docx", "Lease_Agreement_Westlands.doc", "~$ntract_FINAL_v3.docx",
    "email_from_client.eml", "meeting_notes.txt",
    "voice_note.mp3", "ID_scan_backup.zip", "README",
]

folder = Path("client_downloads")
folder.mkdir(exist_ok=True)
for name in FILES:
    (folder / name).write_text("dummy file for testing\n", encoding="utf-8")

# A file that will clash with one already sorted earlier
(folder / "Filings").mkdir(exist_ok=True)
(folder / "Filings" / "scan001.pdf").write_text("sorted last week\n", encoding="utf-8")

print(f"Created {len(FILES)} test files in {folder.resolve()}")
print('Now run:  python sort_files.py client_downloads')
