import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import fitz  # PyMuPDF
import requests
from loguru import logger
import magic
from tenacity import retry, stop_after_attempt, wait_exponential

class PDFProcessor:
    def __init__(self, download_dir: str = "./data/raw_papers"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        # Headers for PDF downloads
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def download_pdf(self, url: str, filename: str) -> Optional[str]:
        """Download PDF from URL and return local file path"""
        try:
            if not url:
                logger.warning("Empty URL provided for PDF download")
                return None
            
            file_path = self.download_dir / filename
            
            # Skip if file already exists
            if file_path.exists():
                logger.info(f"PDF already exists: {filename}")
                return str(file_path)
            
            logger.info(f"Downloading PDF: {url}")
            
            response = requests.get(url, headers=self.headers, timeout=30, stream=True)
            response.raise_for_status()
            
            # Check if response is actually a PDF
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' not in content_type and 'application/octet-stream' not in content_type:
                logger.warning(f"URL does not appear to be a PDF: {url} (content-type: {content_type})")
                return None
            
            # Write file in chunks
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verify the downloaded file is actually a PDF
            if not self._is_valid_pdf(file_path):
                logger.warning(f"Downloaded file is not a valid PDF: {filename}")
                file_path.unlink()  # Delete invalid file
                return None
            
            logger.info(f"Successfully downloaded PDF: {filename}")
            return str(file_path)
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading PDF from {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading PDF: {e}")
            return None
    
    def _is_valid_pdf(self, file_path: Path) -> bool:
        """Check if file is a valid PDF using magic"""
        try:
            if not file_path.exists():
                return False
            
            # Check file magic
            file_type = magic.from_file(str(file_path), mime=True)
            if 'pdf' not in file_type.lower():
                return False
            
            # Try to open with PyMuPDF
            doc = fitz.open(str(file_path))
            page_count = doc.page_count
            doc.close()
            
            return page_count > 0
        
        except Exception as e:
            logger.error(f"Error validating PDF {file_path}: {e}")
            return False
    
    def extract_text_from_pdf(self, file_path: str) -> Dict[str, str]:
        """Extract text from PDF with section identification"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"PDF file not found: {file_path}")
                return {}
            
            doc = fitz.open(file_path)
            
            if doc.page_count == 0:
                logger.warning(f"PDF has no pages: {file_path}")
                return {}
            
            # Extract text from all pages
            full_text = ""
            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                text = page.get_text()
                full_text += text + "\n"
            
            doc.close()
            
            # Parse sections
            sections = self._parse_sections(full_text)
            
            return {
                'full_text': full_text.strip(),
                'sections': sections,
                'page_count': doc.page_count,
                'word_count': len(full_text.split())
            }
        
        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {e}")
            return {}
    
    def _parse_sections(self, text: str) -> Dict[str, str]:
        """Parse PDF text into standard academic sections"""
        sections = {
            'abstract': '',
            'introduction': '',
            'methods': '',
            'results': '',
            'discussion': '',
            'conclusion': '',
            'references': ''
        }
        
        # Common section patterns
        patterns = {
            'abstract': [
                r'\babstract\b.*?(?=\n\s*\n|\b(?:introduction|keywords|1\.)\b)',
                r'\bsummary\b.*?(?=\n\s*\n|\b(?:introduction|keywords|1\.)\b)'
            ],
            'introduction': [
                r'\bintroduction\b.*?(?=\n\s*\n|\b(?:methods?|materials?|methodology|2\.)\b)',
                r'\b1\.?\s*introduction\b.*?(?=\n\s*\n|\b(?:methods?|materials?|methodology|2\.)\b)'
            ],
            'methods': [
                r'\b(?:methods?|materials?|methodology)\b.*?(?=\n\s*\n|\b(?:results?|findings|3\.)\b)',
                r'\b2\.?\s*(?:methods?|materials?|methodology)\b.*?(?=\n\s*\n|\b(?:results?|findings|3\.)\b)'
            ],
            'results': [
                r'\b(?:results?|findings)\b.*?(?=\n\s*\n|\b(?:discussion|conclusions?|4\.)\b)',
                r'\b3\.?\s*(?:results?|findings)\b.*?(?=\n\s*\n|\b(?:discussion|conclusions?|4\.)\b)'
            ],
            'discussion': [
                r'\bdiscussion\b.*?(?=\n\s*\n|\b(?:conclusions?|references|5\.)\b)',
                r'\b4\.?\s*discussion\b.*?(?=\n\s*\n|\b(?:conclusions?|references|5\.)\b)'
            ],
            'conclusion': [
                r'\b(?:conclusions?|concluding remarks)\b.*?(?=\n\s*\n|\b(?:references|acknowledgments)\b)',
                r'\b5\.?\s*(?:conclusions?|concluding remarks)\b.*?(?=\n\s*\n|\b(?:references|acknowledgments)\b)'
            ],
            'references': [
                r'\b(?:references|bibliography)\b.*$',
                r'\b(?:6\.?\s*)?(?:references|bibliography)\b.*$'
            ]
        }
        
        text_lower = text.lower()
        
        for section_name, section_patterns in patterns.items():
            for pattern in section_patterns:
                match = re.search(pattern, text_lower, re.DOTALL | re.IGNORECASE)
                if match:
                    # Extract the matched section from the original text (preserving case)
                    start_pos = match.start()
                    end_pos = match.end()
                    section_text = text[start_pos:end_pos].strip()
                    
                    # Clean up the section text
                    section_text = self._clean_section_text(section_text)
                    
                    if len(section_text) > 50:  # Only include substantial sections
                        sections[section_name] = section_text
                        break
        
        return sections
    
    def _clean_section_text(self, text: str) -> str:
        """Clean extracted section text"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove page numbers and headers/footers
        text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
        
        # Remove figure/table references that appear on separate lines
        text = re.sub(r'\n\s*(?:Figure|Table|Fig\.)\s+\d+.*?\n', '\n', text, flags=re.IGNORECASE)
        
        # Clean up line breaks
        text = re.sub(r'\n+', '\n', text)
        
        return text.strip()
    
    def extract_metadata_from_pdf(self, file_path: str) -> Dict[str, any]:
        """Extract metadata from PDF file"""
        try:
            doc = fitz.open(file_path)
            metadata = doc.metadata
            doc.close()
            
            # Clean and structure metadata
            cleaned_metadata = {}
            
            if metadata.get('title'):
                cleaned_metadata['pdf_title'] = metadata['title'].strip()
            
            if metadata.get('author'):
                cleaned_metadata['pdf_author'] = metadata['author'].strip()
            
            if metadata.get('subject'):
                cleaned_metadata['pdf_subject'] = metadata['subject'].strip()
            
            if metadata.get('creator'):
                cleaned_metadata['pdf_creator'] = metadata['creator'].strip()
            
            if metadata.get('producer'):
                cleaned_metadata['pdf_producer'] = metadata['producer'].strip()
            
            if metadata.get('creationDate'):
                cleaned_metadata['pdf_creation_date'] = metadata['creationDate']
            
            if metadata.get('modDate'):
                cleaned_metadata['pdf_modification_date'] = metadata['modDate']
            
            return cleaned_metadata
        
        except Exception as e:
            logger.error(f"Error extracting PDF metadata from {file_path}: {e}")
            return {}
    
    def process_pdf_complete(self, pdf_url: str, paper_id: str) -> Dict[str, any]:
        """Complete PDF processing pipeline"""
        try:
            # Generate filename
            filename = f"{paper_id}.pdf"
            
            # Download PDF
            file_path = self.download_pdf(pdf_url, filename)
            if not file_path:
                return {'success': False, 'error': 'Failed to download PDF'}
            
            # Extract text and sections
            text_data = self.extract_text_from_pdf(file_path)
            if not text_data:
                return {'success': False, 'error': 'Failed to extract text from PDF'}
            
            # Extract metadata
            pdf_metadata = self.extract_metadata_from_pdf(file_path)
            
            return {
                'success': True,
                'file_path': file_path,
                'full_text': text_data['full_text'],
                'sections': text_data['sections'],
                'page_count': text_data.get('page_count', 0),
                'word_count': text_data.get('word_count', 0),
                'pdf_metadata': pdf_metadata
            }
        
        except Exception as e:
            logger.error(f"Error in complete PDF processing: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_processing_stats(self) -> Dict[str, int]:
        """Get statistics about downloaded PDFs"""
        try:
            pdf_files = list(self.download_dir.glob("*.pdf"))
            
            total_size = sum(f.stat().st_size for f in pdf_files)
            
            return {
                'total_pdfs': len(pdf_files),
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'avg_size_mb': round(total_size / len(pdf_files) / (1024 * 1024), 2) if pdf_files else 0
            }
        
        except Exception as e:
            logger.error(f"Error getting PDF processing stats: {e}")
            return {'total_pdfs': 0, 'total_size_mb': 0, 'avg_size_mb': 0}