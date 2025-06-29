import os
from typing import Dict, List, Optional, Tuple
import json
from dataclasses import asdict
from openai import OpenAI
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from ..collectors.base_collector import PaperMetadata

class AIFilter:
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.rate_limit_rpm = 60  # requests per minute
        
        # Domain-specific criteria for sports science
        self.domain_criteria = {
            'load_progression': {
                'keywords': ['progressive overload', 'training load', 'autoregulation', 'RPE', 'volume progression'],
                'study_types': ['randomized controlled trial', 'longitudinal study', 'intervention study'],
                'populations': ['athletes', 'trained individuals', 'resistance training']
            },
            'deload_timing': {
                'keywords': ['deload', 'tapering', 'recovery', 'fatigue monitoring', 'overreaching', 'supercompensation'],
                'study_types': ['experimental study', 'longitudinal study', 'case study'],
                'populations': ['athletes', 'trained individuals', 'competitive athletes']
            },
            'exercise_selection': {
                'keywords': ['exercise selection', 'biomechanics', 'muscle activation', 'EMG', 'movement patterns'],
                'study_types': ['comparative study', 'cross-sectional study', 'experimental study'],
                'populations': ['healthy adults', 'athletes', 'trained individuals']
            },
            'periodization': {
                'keywords': ['periodization', 'training programming', 'block periodization', 'linear periodization', 'undulating'],
                'study_types': ['randomized controlled trial', 'longitudinal study', 'comparative study'],
                'populations': ['athletes', 'trained individuals', 'competitive athletes']
            }
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def assess_paper_relevance(self, paper: PaperMetadata, domain: str) -> Dict[str, any]:
        """Assess paper relevance using AI"""
        try:
            criteria = self.domain_criteria.get(domain, {})
            
            prompt = self._build_assessment_prompt(paper, domain, criteria)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert sports science researcher evaluating academic papers for relevance and quality."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            result = response.choices[0].message.content
            return self._parse_ai_response(result)
        
        except Exception as e:
            logger.error(f"Error in AI assessment: {e}")
            return {
                'relevance_score': 0.5,
                'quality_score': 5,
                'reasoning': f"AI assessment failed: {str(e)}",
                'key_findings': [],
                'methodology_assessment': 'unknown',
                'population_relevance': 'unknown'
            }
    
    def _build_assessment_prompt(self, paper: PaperMetadata, domain: str, criteria: Dict) -> str:
        """Build assessment prompt for AI"""
        
        prompt = f"""
Please evaluate this sports science research paper for the domain: {domain.upper()}

PAPER DETAILS:
Title: {paper.title}
Authors: {', '.join(paper.authors) if paper.authors else 'N/A'}
Journal: {paper.journal or 'N/A'}
Year: {paper.year or 'N/A'}
Abstract: {paper.abstract[:1000] if paper.abstract else 'N/A'}

DOMAIN CRITERIA:
- Key concepts: {', '.join(criteria.get('keywords', []))}
- Preferred study types: {', '.join(criteria.get('study_types', []))}
- Target populations: {', '.join(criteria.get('populations', []))}

Please provide a JSON response with the following structure:
{{
    "relevance_score": <float 0-1>,
    "quality_score": <int 1-10>,
    "reasoning": "<brief explanation>",
    "key_findings": ["<finding1>", "<finding2>"],
    "methodology_assessment": "<experimental/observational/review/meta-analysis/case-study>",
    "population_relevance": "<high/medium/low>",
    "practical_applications": "<brief description>",
    "limitations": "<key limitations if any>"
}}

SCORING GUIDELINES:
- Relevance Score (0-1): How well does this paper address the domain topics?
- Quality Score (1-10): Research methodology quality, sample size, controls, etc.
- Consider: study design, sample size, statistical methods, practical applicability

Provide only the JSON response, no additional text.
"""
        return prompt
    
    def _parse_ai_response(self, response: str) -> Dict[str, any]:
        """Parse AI response into structured data"""
        try:
            # Try to extract JSON from response
            response = response.strip()
            if response.startswith('```json'):
                response = response[7:-3]
            elif response.startswith('```'):
                response = response[3:-3]
            
            result = json.loads(response)
            
            # Validate and clean the response
            cleaned_result = {
                'relevance_score': max(0.0, min(1.0, float(result.get('relevance_score', 0.5)))),
                'quality_score': max(1, min(10, int(result.get('quality_score', 5)))),
                'reasoning': str(result.get('reasoning', 'No reasoning provided'))[:500],
                'key_findings': result.get('key_findings', [])[:5],  # Limit to 5 findings
                'methodology_assessment': str(result.get('methodology_assessment', 'unknown')),
                'population_relevance': str(result.get('population_relevance', 'unknown')),
                'practical_applications': str(result.get('practical_applications', ''))[:300],
                'limitations': str(result.get('limitations', ''))[:300]
            }
            
            return cleaned_result
        
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Error parsing AI response: {e}")
            logger.debug(f"Raw response: {response}")
            
            # Return default values if parsing fails
            return {
                'relevance_score': 0.5,
                'quality_score': 5,
                'reasoning': 'Failed to parse AI response',
                'key_findings': [],
                'methodology_assessment': 'unknown',
                'population_relevance': 'unknown',
                'practical_applications': '',
                'limitations': ''
            }
    
    def batch_assess_papers(
        self, 
        papers: List[PaperMetadata], 
        domain: str,
        min_relevance_score: float = 0.6,
        min_quality_score: int = 6
    ) -> List[Tuple[PaperMetadata, Dict[str, any]]]:
        """Assess multiple papers and filter by thresholds"""
        
        results = []
        
        for i, paper in enumerate(papers):
            try:
                logger.info(f"Assessing paper {i+1}/{len(papers)}: {paper.title[:50]}...")
                
                assessment = self.assess_paper_relevance(paper, domain)
                
                # Check if paper meets minimum thresholds
                if (assessment['relevance_score'] >= min_relevance_score and 
                    assessment['quality_score'] >= min_quality_score):
                    
                    results.append((paper, assessment))
                    logger.info(f"Paper accepted - Relevance: {assessment['relevance_score']:.2f}, Quality: {assessment['quality_score']}")
                else:
                    logger.info(f"Paper rejected - Relevance: {assessment['relevance_score']:.2f}, Quality: {assessment['quality_score']}")
            
            except Exception as e:
                logger.error(f"Error assessing paper {i+1}: {e}")
                continue
        
        logger.info(f"Batch assessment complete: {len(results)}/{len(papers)} papers accepted")
        return results
    
    def assess_paper_with_full_text(
        self, 
        paper: PaperMetadata, 
        full_text: str, 
        domain: str
    ) -> Dict[str, any]:
        """Assess paper using full text (more comprehensive)"""
        try:
            criteria = self.domain_criteria.get(domain, {})
            
            # Truncate full text to fit within token limits
            truncated_text = full_text[:3000] if full_text else ""
            
            prompt = f"""
Please evaluate this sports science research paper for the domain: {domain.upper()}

PAPER DETAILS:
Title: {paper.title}
Authors: {', '.join(paper.authors) if paper.authors else 'N/A'}
Journal: {paper.journal or 'N/A'}
Year: {paper.year or 'N/A'}

ABSTRACT:
{paper.abstract[:500] if paper.abstract else 'N/A'}

FULL TEXT EXCERPT:
{truncated_text}

DOMAIN CRITERIA:
- Key concepts: {', '.join(criteria.get('keywords', []))}
- Preferred study types: {', '.join(criteria.get('study_types', []))}
- Target populations: {', '.join(criteria.get('populations', []))}

Please provide a comprehensive JSON assessment with the same structure as before,
but now with access to the full text, provide more detailed analysis.

Focus on:
1. Specific methodology used
2. Sample characteristics
3. Key findings and their practical relevance
4. Statistical analysis quality
5. Limitations and future directions

Provide only the JSON response, no additional text.
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert sports science researcher with deep knowledge of training methodology, exercise physiology, and biomechanics."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=800
            )
            
            result = response.choices[0].message.content
            return self._parse_ai_response(result)
        
        except Exception as e:
            logger.error(f"Error in comprehensive AI assessment: {e}")
            return self.assess_paper_relevance(paper, domain)  # Fallback to basic assessment
    
    def get_domain_summary(self, papers_with_assessments: List[Tuple[PaperMetadata, Dict]], domain: str) -> Dict[str, any]:
        """Generate summary of assessed papers for a domain"""
        try:
            if not papers_with_assessments:
                return {}
            
            total_papers = len(papers_with_assessments)
            
            # Calculate averages
            avg_relevance = sum(assessment['relevance_score'] for _, assessment in papers_with_assessments) / total_papers
            avg_quality = sum(assessment['quality_score'] for _, assessment in papers_with_assessments) / total_papers
            
            # Count methodologies
            methodologies = {}
            populations = {}
            
            for _, assessment in papers_with_assessments:
                method = assessment.get('methodology_assessment', 'unknown')
                methodologies[method] = methodologies.get(method, 0) + 1
                
                pop = assessment.get('population_relevance', 'unknown')
                populations[pop] = populations.get(pop, 0) + 1
            
            # Collect all key findings
            all_findings = []
            for _, assessment in papers_with_assessments:
                all_findings.extend(assessment.get('key_findings', []))
            
            return {
                'domain': domain,
                'total_papers': total_papers,
                'average_relevance_score': round(avg_relevance, 3),
                'average_quality_score': round(avg_quality, 1),
                'methodology_distribution': methodologies,
                'population_relevance_distribution': populations,
                'key_findings_count': len(all_findings),
                'unique_findings': len(set(all_findings))
            }
        
        except Exception as e:
            logger.error(f"Error generating domain summary: {e}")
            return {}