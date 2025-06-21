import pandas as pd
import asyncio
import json  
import aiohttp
import logging
import json
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Tuple, Set
from tavily import TavilyClient
from openai import OpenAI
from bs4 import BeautifulSoup
import re
import nest_asyncio
from urllib.parse import urlparse
import time
from news_letter_sender import NewsletterEmailer

# Enable nested event loops (useful for Jupyter)
nest_asyncio.apply()

@dataclass
class Article:
    title: str
    url: str
    published_date: str
    content: str
    domain: str
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    entities: Optional[str] = None
    relevance_score: Optional[float] = None
    company_mentions: Optional[int] = None
    
    def to_dict(self) -> Dict:
        """Convert article to dictionary for JSON serialization"""
        return asdict(self)

class EnhancedTechNewsAnalyzer:
    def __init__(self,
                 mail: str,
                 tavily_api_key: str,
                 openai_api_key: str,
                 frequency: str,
                 companies: List[str] = None,
                 max_workers: int = 8,
                 request_timeout: int = 20,
                 max_articles_per_company: int = 15,
                 rate_limit_delay: float = 0.5,
                 relevance_threshold: float = 0.15,
                 output_file: Optional[str] = None,
                 search_iterations: int = 3):
        """
        Enhanced TechNewsAnalyzer with simplified domain handling
        
        Args:
            tavily_api_key: Tavily API key for news search
            openai_api_key: OpenAI API key for content analysis
            frequency: Time range for news ('day', 'week', 'month')
            companies: List of companies to analyze (required)
            max_workers: Maximum concurrent workers
            request_timeout: Request timeout in seconds
            max_articles_per_company: Maximum articles per company
            rate_limit_delay: Delay between requests
            relevance_threshold: Relevance threshold (0.0-1.0)
            output_file: Optional file path to save JSON output
            search_iterations: Number of search iterations per company
        """
        # Set up logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Validate required parameters
        if not companies:
            raise ValueError("Companies list cannot be empty")
        
        # Configuration
        self.mail=mail
        self.tavily_api_key = tavily_api_key
        self.openai_api_key = openai_api_key
        self.frequency = frequency
        self.companies = [self._normalize_company_name(comp) for comp in companies]
        self.max_workers = max_workers
        self.request_timeout = request_timeout
        self.max_articles_per_company = max_articles_per_company
        self.rate_limit_delay = rate_limit_delay
        self.relevance_threshold = relevance_threshold
        self.output_file = output_file
        self.search_iterations = search_iterations
        
        # Initialize clients
        self.tavily_client = TavilyClient(api_key=self.tavily_api_key)
        self.openai_client = OpenAI(api_key=self.openai_api_key)
        self.session = None
        self.results = {}
        self.processed_urls = set()  # Track processed URLs to avoid duplicates
        
        # Tech terms categories (simplified)
        self.tech_categories = {
            'ai_ml': ['AI', 'artificial intelligence', 'machine learning', 'deep learning', 'neural network', 
                     'LLM', 'generative AI', 'ChatGPT', 'transformer', 'NLP'],
            'cloud': ['cloud computing', 'AWS', 'Azure', 'GCP', 'serverless', 'containerization', 
                     'Kubernetes', 'Docker', 'microservices'],
            'data': ['big data', 'analytics', 'data science', 'blockchain', 'cryptocurrency', 
                    'database', 'data warehouse', 'ETL'],
            'security': ['cybersecurity', 'encryption', 'zero trust', 'firewall', 'vulnerability', 
                        'breach', 'malware', 'ransomware'],
            'business': ['acquisition', 'merger', 'partnership', 'IPO', 'funding', 'valuation', 
                        'revenue', 'earnings', 'launch', 'product']
        }
        
        # Flatten all tech terms
        self.all_tech_terms = []
        for category_terms in self.tech_categories.values():
            self.all_tech_terms.extend(category_terms)

    def _normalize_company_name(self, company_name: str) -> str:
        """Normalize company name for consistent processing"""
        # Remove common suffixes and clean up
        suffixes = ['Inc', 'Inc.', 'Corp', 'Corp.', 'LLC', 'Ltd', 'Ltd.', 'Co.', 'Company', 'Technologies']
        normalized = company_name.strip()
        
        for suffix in suffixes:
            if normalized.endswith(f' {suffix}'):
                normalized = normalized[:-len(f' {suffix}')]
        
        return normalized.strip()

    async def __aenter__(self):
        """Async context manager entry"""
        connector = aiohttp.TCPConnector(limit=50, limit_per_host=10)
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.request_timeout),
            connector=connector,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    def build_comprehensive_queries(self, company_name: str) -> List[str]:
        """Build optimized search queries with strict company matching"""
        queries = []
        
        # Strict company name matching (exact phrase and common variations)
        company_variations = [
            f'"{company_name}"',                     # Exact match
            f'"{company_name} Inc"',                 # Common suffix
            f'"{company_name} Corp"',               # Alternative suffix
            f'"{company_name.split()[0]}"',          # First word only (for common names)
        ]
        
        # Dedupe variations
        company_variations = list(set(company_variations))
        
        # Tech context combinations
        tech_contexts = [
            ("technology", self.tech_categories['ai_ml'][:3]),  # AI focus
            ("business", self.tech_categories['business'][:3]), # Business focus
            ("product", ["launch", "release", "new"]),         # Product news
            ("partnership", ["partner", "collaborate", "deal"]) # Partnerships
        ]
        
        # Build queries combining company variations with contexts
        for variation in company_variations:
            for context_name, terms in tech_contexts:
                terms_str = " OR ".join(terms)
                queries.append(f"{variation} AND ({terms_str})")
        
        # Add pure company queries (less strict but with relevance threshold)
        queries.extend(company_variations)
        
        # Ensure queries don't exceed length limits and are unique
        unique_queries = list(set(query[:450] for query in queries))
        return unique_queries[:10]  # Limit to 10 best queries
    async def validate_article_relevance(self, article: Article, company_name: str) -> bool:
        """Post-processing validation of article relevance"""
        # Check if company is mentioned in both title and content
        title_mentions = article.title.lower().count(company_name.lower())
        content_mentions = article.content.lower().count(company_name.lower())
        
        if title_mentions == 0 and content_mentions == 0:
            return False
        
        # Check if summary actually mentions the company
        if company_name.lower() not in article.summary.lower():
            return False
        
        # Check for sufficient content length
        if len(article.content) < 200:
            return False
        
        # Check for at least one tech/business term
        combined_text = f"{article.title} {article.content}".lower()
        if not any(term.lower() in combined_text for term in self.all_tech_terms):
            return False
        
        return True
    async def _safe_tavily_search(self, query: str) -> Optional[Dict]:
        """Wrapper for Tavily search with better error handling"""
        try:
            return await asyncio.to_thread(
                self.tavily_client.search,
                query=query,
                topic="news",
                search_depth="advanced",
                max_results=20,
                time_range=self.frequency,
                include_raw_content=True,
            )
        except Exception as e:
            self.logger.error(f"Tavily API error for query '{query}': {str(e)}")
            return None

    async def get_comprehensive_news(self, company_name: str) -> List[Dict]:
        """Get news from multiple search iterations"""
        all_results = []
        seen_urls = set()
        queries = self.build_comprehensive_queries(company_name)
        
        for iteration in range(self.search_iterations):
            current_query = queries[iteration % len(queries)]
            
            self.logger.info(f"Search iteration {iteration + 1} for {company_name} with query: {current_query}")
            
            try:
                # Add explicit timeout and error handling
                response = await asyncio.wait_for(
                    self._safe_tavily_search(current_query),
                    timeout=self.request_timeout
                )
                
                if not response or 'results' not in response:
                    continue
                    
                results = response['results']
                
                for result in results:
                    url = result.get('url', '')
                    if (url not in seen_urls and 
                        result.get('published_date') not in [None, '', 'Date unknown']):
                        
                        relevance_score = self._calculate_enhanced_relevance(
                            result.get('title', ''), 
                            result.get('content', ''), 
                            company_name
                        )
                        
                        if relevance_score >= self.relevance_threshold:
                            result['relevance_score'] = relevance_score
                            result['domain'] = self._extract_domain_from_url(url)
                            all_results.append(result)
                            seen_urls.add(url)
                
                # Rate limiting between searches
                await asyncio.sleep(self.rate_limit_delay * 2)
                
            except Exception as e:
                self.logger.error(f"Search iteration {iteration + 1} failed for {company_name}: {e}")
                continue
        
        # Sort by relevance and limit results
        all_results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        return all_results[:self.max_articles_per_company]


    def _extract_domain_from_url(self, url: str) -> str:
        """Extract clean domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return "unknown"

    def _calculate_enhanced_relevance(self, title: str, content: str, company_name: str) -> float:
        """Enhanced relevance calculation with stronger company focus"""
        combined_text = f"{title} {content}".lower()
        company_lower = company_name.lower()
        
        relevance_score = 0.0
        
        # Stronger weighting for company mentions
        title_mentions = title.lower().count(company_lower)
        content_mentions = combined_text.count(company_lower)
        
        # Title mentions are very valuable
        relevance_score += min(0.5, title_mentions * 0.3 + content_mentions * 0.1)
        
        # Bonus for company appearing in first 100 characters of content
        if content[:100].lower().count(company_lower) > 0:
            relevance_score += 0.1
        
        # Tech category relevance (secondary to company mentions)
        category_scores = {}
        for category, terms in self.tech_categories.items():
            matches = sum(1 for term in terms if term.lower() in combined_text)
            if matches > 0:
                category_scores[category] = matches
        
        if category_scores:
            max_category_score = max(category_scores.values())
            relevance_score += min(0.2, max_category_score * 0.02)
        
        # Content quality indicators
        if len(content) > 800:
            relevance_score += 0.05
        
        # Strong penalty if company not mentioned in content at all
        if content_mentions == 0:
            relevance_score *= 0.5
        
        return min(1.0, max(0.0, relevance_score))


    async def get_enhanced_article_text(self, url: str) -> Optional[str]:
        """Enhanced article text extraction with multiple fallback strategies"""
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    return None
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Remove unwanted elements
                for element in soup(['script', 'style', 'nav', 'footer', 'iframe', 
                                   'img', 'figure', 'advertisement', 'aside', 'header',
                                   'menu', 'form', 'button']):
                    element.decompose()
                
                # Try multiple content extraction strategies
                content = self._extract_content_multiple_strategies(soup)
                
                if content and len(content.strip()) > 300:
                    return self._clean_and_truncate_text(content)
                
                return None
                
        except Exception as e:
            self.logger.debug(f"Failed to extract text from {url}: {e}")
            return None

    def _extract_content_multiple_strategies(self, soup: BeautifulSoup) -> str:
        """Try multiple strategies to extract main content"""
        strategies = [
            # Strategy 1: Semantic HTML5 elements
            lambda s: s.find('article'),
            lambda s: s.find('main'),
            
            # Strategy 2: Common content selectors
            lambda s: s.select_one('[class*="content"]'),
            lambda s: s.select_one('[class*="article"]'),
            lambda s: s.select_one('[class*="post-content"]'),
            lambda s: s.select_one('[class*="entry-content"]'),
            lambda s: s.select_one('[id*="content"]'),
            lambda s: s.select_one('[id*="article"]'),
            
            # Strategy 3: Paragraph-based extraction
            lambda s: self._extract_paragraph_content(s),
            
            # Strategy 4: Fallback to body
            lambda s: s.body if s.body else s
        ]
        
        for strategy in strategies:
            try:
                element = strategy(soup)
                if element:
                    text = element.get_text(separator='\n', strip=True)
                    if len(text) > 500:  # Minimum content length
                        return text
            except:
                continue
        
        return ""

    def _extract_paragraph_content(self, soup: BeautifulSoup) -> Optional[BeautifulSoup]:
        """Extract content based on paragraph density"""
        # Find the section with the most paragraphs
        containers = soup.find_all(['div', 'section', 'article'])
        best_container = None
        max_paragraphs = 0
        
        for container in containers:
            paragraphs = container.find_all('p')
            if len(paragraphs) > max_paragraphs:
                max_paragraphs = len(paragraphs)
                best_container = container
        
        return best_container

    def _clean_and_truncate_text(self, text: str) -> str:
        """Enhanced text cleaning and truncation"""
        # Split into lines and clean
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        
        # Filter out short chunks and noise
        meaningful_chunks = []
        for chunk in chunks:
            if (len(chunk) > 15 and 
                not self._is_noise_text(chunk) and
                not chunk.startswith(('©', 'Copyright', 'All rights reserved'))):
                meaningful_chunks.append(chunk)
        
        cleaned = '\n'.join(meaningful_chunks)
        
        # Remove common noise patterns
        noise_patterns = [
            r'cookie policy.*?(?=\n|$)', r'privacy policy.*?(?=\n|$)', 
            r'terms of service.*?(?=\n|$)', r'subscribe.*?newsletter.*?(?=\n|$)',
            r'follow us on.*?(?=\n|$)', r'share this.*?(?=\n|$)',
            r'read more.*?(?=\n|$)', r'continue reading.*?(?=\n|$)',
            r'related articles.*?(?=\n|$)', r'advertisement.*?(?=\n|$)'
        ]
        
        for pattern in noise_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
        
        # Truncate to reasonable length
        return cleaned[:20000]

    def _is_noise_text(self, text: str) -> bool:
        """Identify noise text that should be filtered out"""
        noise_indicators = [
            'cookie', 'privacy policy', 'terms of service', 'subscribe',
            'newsletter', 'advertisement', 'sponsored', 'affiliate',
            'click here', 'read more', 'continue reading', 'related articles',
            'share this', 'follow us', 'social media', 'comment below'
        ]
        
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in noise_indicators)

    def analyze_content_with_ai(self, title: str, content: str, company_name: str) -> Tuple[str, str, str]:
        """AI analysis with guaranteed summary fallback"""
        if not content or len(content.strip()) < 100:
            return self._enhanced_fallback_analysis(title, content, company_name)
        
        try:
            prompt = f"""
    Analyze this news article about {company_name}. Focus specifically on {company_name}'s role and actions.

    Article Title: {title}
    Article Content: {content[:15000]}

    Provide your analysis in EXACTLY this format:

    SUMMARY: [2-3 specific sentences about {company_name}'s involvement. Must mention {company_name} directly.]

    SENTIMENT: [Positive, Negative, or Neutral]

    ENTITIES: [4-6 specific terms related to {company_name}]

    If the content doesn't mention {company_name}, say "Not directly about {company_name}" in SUMMARY.
    """
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": f"You are a business analyst. Always provide a SUMMARY mentioning {company_name}."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=800
            )
            
            analysis_text = response.choices[0].message.content.strip()
            summary, sentiment, entities = self._parse_analysis_response(analysis_text)
            
            # Fallback if summary doesn't mention company
            if company_name.lower() not in summary.lower():
                return self._enhanced_fallback_analysis(title, content, company_name)
                
            return summary, sentiment, entities
            
        except Exception as e:
            self.logger.error(f"AI analysis failed, using fallback: {e}")
            return self._enhanced_fallback_analysis(title, content, company_name)


    def _parse_analysis_response(self, analysis_text: str) -> Tuple[str, str, str]:
        """Enhanced response parsing with better error handling"""
        summary = "Analysis unavailable"
        sentiment = "Neutral"
        entities = "Not identified"
        
        try:
            lines = [line.strip() for line in analysis_text.split('\n') if line.strip()]
            
            for i, line in enumerate(lines):
                if line.upper().startswith('SUMMARY:'):
                    summary_text = line[8:].strip()
                    # Include next line if summary seems incomplete
                    if i + 1 < len(lines) and not any(lines[i + 1].upper().startswith(prefix) for prefix in ['SENTIMENT:', 'ENTITIES:']):
                        summary_text += " " + lines[i + 1].strip()
                    summary = summary_text
                elif line.upper().startswith('SENTIMENT:'):
                    sentiment_raw = line[10:].strip()
                    if sentiment_raw in ['Positive', 'Negative', 'Neutral']:
                        sentiment = sentiment_raw
                elif line.upper().startswith('ENTITIES:'):
                    entities_raw = line[9:].strip()
                    if entities_raw and len(entities_raw) > 3:
                        entities = entities_raw
                        
        except Exception as e:
            self.logger.debug(f"Error parsing analysis response: {e}")
            
        return summary, sentiment, entities

    def _enhanced_fallback_analysis(self, title: str, content: str, company_name: str) -> Tuple[str, str, str]:
        """Enhanced fallback analysis with guaranteed summary"""
        combined_text = f"{title} {content}".lower()
        
        # Always generate a summary
        sentences = [s.strip() for s in content.split('.') if len(s.strip()) > 30]
        relevant_sentences = []
        
        # Find sentences mentioning the company
        for sentence in sentences[:15]:  # Check first 15 sentences
            if company_name.lower() in sentence.lower():
                relevant_sentences.append(sentence)
            if len(relevant_sentences) >= 2:
                break
        
        if relevant_sentences:
            summary = '. '.join(relevant_sentences[:2]) + "."
        else:
            # If no company mentions, use title + first meaningful sentence
            first_content_sentence = next((s for s in sentences if len(s) > 30), "")
            summary = f"{title}. {first_content_sentence[:300]}"
        
        summary = summary[:500]  # Limit length
        
        # Enhanced sentiment analysis
        positive_words = ['launch', 'partner', 'growth', 'expand', 'innovate', 'achieve', 'success', 'raise', 'invest']
        negative_words = ['layoff', 'cut', 'decline', 'loss', 'fail', 'sue', 'fine', 'warn']
        
        pos_score = sum(1 for word in positive_words if word in combined_text)
        neg_score = sum(1 for word in negative_words if word in combined_text)
        
        if pos_score > neg_score:
            sentiment = "Positive"
        elif neg_score > pos_score:
            sentiment = "Negative"
        else:
            sentiment = "Neutral"
        
        # Enhanced entity extraction
        entities = self._extract_enhanced_entities(content, company_name)
        
        return summary, sentiment, entities



    def _extract_enhanced_entities(self, content: str, company_name: str) -> str:
        """Enhanced entity extraction with better accuracy"""
        entities = set()
        
        # Extract capitalized phrases (potential proper nouns)
        capitalized_patterns = [
            r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b',  # Regular capitalized phrases
            r'\b[A-Z]{2,}\b',  # Acronyms
            r'\b\d+[A-Z]\b'    # Model numbers like 5G, H100
        ]
        
        for pattern in capitalized_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if (len(match) > 2 and 
                    match not in ['The', 'This', 'That', 'They', 'We', 'You', 'It'] and
                    not match.isdigit()):
                    entities.add(match)
        
        # Add relevant tech terms found in content
        content_lower = content.lower()
        for term in self.all_tech_terms:
            if term.lower() in content_lower:
                entities.add(term)
                if len(entities) >= 8:  # Limit to avoid too many
                    break
        
        # Clean and format entities
        cleaned_entities = []
        for entity in entities:
            if len(entity) > 1 and entity not in cleaned_entities:
                cleaned_entities.append(entity)
        
        return ", ".join(cleaned_entities[:6]) if cleaned_entities else "Not identified"
    async def get_supplemental_articles(self, company_name: str) -> List[Article]:
        """Get additional articles when initial results are insufficient"""
        # Try more general queries
        supplemental_queries = [
            f'"{company_name}" latest news',
            f'"{company_name}" recent developments',
            f'"{company_name}" technology updates'
        ]
        
        all_articles = []
        
        for query in supplemental_queries:
            try:
                response = self.tavily_client.search(
                    query=query,
                    topic="news",
                    search_depth="basic",
                    max_results=10,
                    time_range=self.frequency
                )
                
                new_articles = [
                    article for article in response.get('results', [])
                    if article['url'] not in self.processed_urls
                ]
                
                if new_articles:
                    processed = await self.process_articles_batch(new_articles, company_name)
                    all_articles.extend(processed)
                    
                    if len(all_articles) >= 5:  # Stop if we have enough
                        break
                        
            except Exception as e:
                self.logger.debug(f"Supplemental search failed for {query}: {e}")
        
        return all_articles

    async def process_articles_batch(self, articles_data: List[Dict], company_name: str) -> List[Article]:
        """Updated batch processing with relevance validation"""
        articles = []
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def process_single_article(article_data, index):
            async with semaphore:
                try:
                    url = article_data['url']
                    
                    if url in self.processed_urls:
                        return None
                    
                    self.processed_urls.add(url)
                    
                    # Extract article text with fallback
                    article_text = await self.get_enhanced_article_text(url) or article_data.get('content', '')
                    
                    # Rate limiting between requests
                    await asyncio.sleep(self.rate_limit_delay)
                    
                    # Analyze content
                    summary, sentiment, entities = self.analyze_content_with_ai(
                        article_data['title'], article_text, company_name
                    )
                    
                    # Create article object
                    article = Article(
                        title=article_data['title'],
                        url=url,
                        published_date=article_data['published_date'],
                        content=article_text[:2000],
                        domain=article_data.get('domain', self._extract_domain_from_url(url)),
                        summary=summary,
                        sentiment=sentiment,
                        entities=entities,
                        relevance_score=article_data.get('relevance_score', 0),
                        company_mentions=(
                            article_data['title'].lower().count(company_name.lower()) +
                            article_text.lower().count(company_name.lower())
                        )
                    )
                    
                    # Validate relevance before including
                    if await self.validate_article_relevance(article, company_name):
                        return article
                    return None
                    
                except Exception as e:
                    self.logger.debug(f"Error processing article {index}: {e}")
                    return None
        
        # Process with parallel limits
        tasks = [process_single_article(article_data, i) 
                for i, article_data in enumerate(articles_data)]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful results
        articles = [result for result in results if isinstance(result, Article)]
        
        # If we don't have enough relevant articles, try additional searches
        if len(articles) < min(5, self.max_articles_per_company):
            self.logger.info(f"Only {len(articles)} relevant articles found for {company_name}, doing supplemental search")
            supplemental_articles = await self.get_supplemental_articles(company_name)
            articles.extend(supplemental_articles)
        
        return articles[:self.max_articles_per_company]

    def generate_comprehensive_json_output(self) -> Dict:
        """Generate simplified JSON output with only specified fields and top 15 articles across all companies"""
        output = {
            "companies": {},
            "analytics": {
                "total_companies": len(self.companies),
                "total_articles_found": 0,
                "sentiment_distribution": {"Positive": 0, "Negative": 0, "Neutral": 0},
                "top_entities": {}
            }
        }
        
        # Collect all articles from all companies that:
        # 1. Don't have summaries starting with "Not directly about"
        # 2. Directly mention the company in summary
        all_articles = []
        for company_name, articles in self.results.items():
            for article in articles:
                # Skip articles with "Not directly about" in summary
                if article.summary and article.summary.startswith("Not directly about"):
                    continue
                    
                # Check if summary directly mentions the company (case insensitive)
                if article.summary and company_name.lower() in article.summary.lower():
                    all_articles.append({
                        "company": company_name,
                        "article_obj": article,
                        "relevance_score": article.relevance_score or 0
                    })
        
        # Sort all qualifying articles by relevance score (descending) and take top 15
        top_articles = sorted(all_articles, key=lambda x: x["relevance_score"], reverse=True)[:15]
        total_articles = len(top_articles)
        
        entity_counts = {}
        
        # Organize articles by company for the output
        for article_info in top_articles:
            company_name = article_info["company"]
            article = article_info["article_obj"]
            
            # Initialize company entry if not exists
            if company_name not in output["companies"]:
                output["companies"][company_name] = {
                    "article_count": 0,
                    "articles": []
                }
            
            # Convert article to simplified dictionary
            article_dict = {
                "company": company_name,
                "title": article.title,
                "summary": article.summary,
                "url": article.url,
                "sentiment": article.sentiment,
                "entities": article.entities,
                "relevance_score": article.relevance_score
            }
            
            output["companies"][company_name]["articles"].append(article_dict)
            output["companies"][company_name]["article_count"] += 1
            
            # Update sentiment distribution
            if article.sentiment in output["analytics"]["sentiment_distribution"]:
                output["analytics"]["sentiment_distribution"][article.sentiment] += 1
            
            # Count entities for global stats
            if article.entities and article.entities != "Not identified":
                entities = [e.strip() for e in article.entities.split(',')]
                for entity in entities:
                    if len(entity) > 2:
                        entity_counts[entity] = entity_counts.get(entity, 0) + 1
        
        # Update global analytics
        output["analytics"]["total_articles_found"] = total_articles
        
        # Top entities (top 15)
        top_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:15]
        output["analytics"]["top_entities"] = dict(top_entities)
        EMAIL_CONFIG = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'email': 'dreamers2k22@gmail.com',
            'password': 'kkdwlmggmfhiscnf'
        }
        
        RECIPIENTS = self.mail.split(" ")
        
        
            # Initialize emailer
        emailer = NewsletterEmailer(**EMAIL_CONFIG)
        
        # Send newsletter
        print("📧 Sending newsletter...")
        success = emailer.send_newsletter(RECIPIENTS, output)
        
        if success:
            print(f"✅ Newsletter sent successfully to {len(RECIPIENTS)} recipients!")
        else:
            print("❌ Failed to send newsletter")
        # print(output)
        return output

    async def run_comprehensive_analysis(self) -> None:  # Returns None since we print directly
        """Main method to run comprehensive analysis and print JSON output"""
        start_time = time.time()
        
        try:
            self.logger.info(f"Starting analysis for {len(self.companies)} companies")
            
            # Process each company
            for i, company in enumerate(self.companies, 1):
                self.logger.info(f"Processing company {i}/{len(self.companies)}: {company}")
                
                try:
                    # Get comprehensive news
                    news_results = await self.get_comprehensive_news(company)
                    
                    if not news_results:
                        self.logger.warning(f"No articles found for {company}")
                        self.results[company] = []
                        continue
                    
                    # Process articles
                    processed_articles = await self.process_articles_batch(news_results, company)
                    self.results[company] = processed_articles
                    
                    self.logger.info(f"Completed {company}: {len(processed_articles)} articles processed")
                        
                except Exception as e:
                    self.logger.error(f"Error processing {company}: {str(e)}")
                    self.results[company] = []
            
            # Generate comprehensive output
            json_output = self.generate_comprehensive_json_output()
            
            # Add processing time
            processing_time = round(time.time() - start_time, 2)
            json_output["analysis_metadata"] = {
                "processing_time": f"{processing_time} seconds",
                "timestamp": datetime.now().isoformat()
            }
            
            # Print JSON directly (formatted with indentation)
            # print(json.dumps(json_output, indent=2, ensure_ascii=False))
            
            self.logger.info(f"Analysis completed in {processing_time} seconds")
                    
        except Exception as e:
            error_output = {
                "error": str(e),
                "processing_time": round(time.time() - start_time, 2)
            }
            print(json.dumps(error_output, indent=2))

    @classmethod
    async def run_analysis(cls, **kwargs) -> str:
        """
        Enhanced class method to run analysis with comprehensive parameters
        
        Usage:
            json_result = await EnhancedTechNewsAnalyzer.run_analysis(
                tavily_api_key=os.getenv("TAVILY_API_KEY"),
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                companies=["Any Company Name", "Another Company"],
                frequency="week",
                max_articles_per_company=20,
                search_iterations=4,
                relevance_threshold=0.1,
                
            )
            print(json_result)
        """
        async with cls(**kwargs) as analyzer:
            result = await analyzer.run_comprehensive_analysis()
            
            # return json.dumps(result, indent=2, ensure_ascii=False)
