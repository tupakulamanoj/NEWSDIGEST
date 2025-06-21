import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from typing import Dict, List, Any
import re
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib import colors

class NewsletterEmailer:
    def __init__(self, smtp_server: str, smtp_port: int, email: str, password: str):
        """
        Initialize the newsletter emailer
        
        Args:
            smtp_server: SMTP server (e.g., 'smtp.gmail.com')
            smtp_port: SMTP port (e.g., 587 for Gmail)
            email: Sender email address
            password: Email password or app password
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = email
        self.password = password
    
    def create_html_newsletter(self, report_data: Dict[str, Any]) -> str:
        """
        Create HTML newsletter from report data
        
        Args:
            report_data: Structured report data
            
        Returns:
            HTML newsletter string
        """
        # Format the generated_at timestamp
        generated_at = report_data.get('metadata', {}).get('generated_at', '')
        if generated_at:
            try:
                dt = datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
                generated_at = dt.strftime('%B %d, %Y at %H:%M')
            except:
                generated_at = ""

        # Get report stats
        total_articles = report_data.get('metadata', {}).get('total_articles', 0)
        companies_count = report_data.get('metadata', {}).get('companies_analyzed', 0)
        report_type = report_data.get('metadata', {}).get('report_type', 'CPRIME NEWS DIGEST')

        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{report_type}</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    background-color: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    border-bottom: 3px solid #2c5aa0;
                    padding-bottom: 25px;
                    margin-bottom: 35px;
                }}
                .header h1 {{
                    color: #2c5aa0;
                    margin: 0 0 10px 0;
                    font-size: 32px;
                    font-weight: 700;
                }}
                .header-subtitle {{
                    color: #666;
                    font-size: 16px;
                    margin: 0 0 15px 0;
                }}
                .report-meta {{
                    text-align: center;
                    font-size: 14px;
                    color: #666;
                    margin-bottom: 20px;
                }}
                .stats-summary {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
                    gap: 15px;
                    margin-bottom: 30px;
                }}
                .stat-card {{
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 8px;
                    text-align: center;
                    border-left: 3px solid #2c5aa0;
                }}
                .stat-number {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #2c5aa0;
                    margin-bottom: 5px;
                }}
                .stat-label {{
                    font-size: 12px;
                    color: #666;
                    text-transform: uppercase;
                }}
                .company-section {{
                    margin-bottom: 40px;
                }}
                .company-name {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #2c5aa0;
                    margin-bottom: 15px;
                    padding-bottom: 5px;
                    border-bottom: 2px solid #e0e0e0;
                }}
                .article {{
                    margin-bottom: 25px;
                    padding: 15px;
                    background-color: #f9f9f9;
                    border-radius: 6px;
                }}
                .article-title {{
                    font-size: 18px;
                    font-weight: bold;
                    margin-bottom: 10px;
                    color: #333;
                }}
                .article-summary {{
                    margin-bottom: 10px;
                    line-height: 1.5;
                }}
                .article-link {{
                    display: inline-block;
                    margin-top: 5px;
                    color: #2c5aa0;
                    text-decoration: none;
                    font-weight: bold;
                }}
                .article-link:hover {{
                    text-decoration: underline;
                }}
                .article-meta {{
                    margin-top: 10px;
                    font-size: 14px;
                }}
                .sentiment {{
                    display: inline-block;
                    padding: 3px 8px;
                    border-radius: 4px;
                    font-size: 13px;
                    margin-right: 10px;
                }}
                .sentiment-positive {{
                    background-color: #d4edda;
                    color: #155724;
                }}
                .sentiment-neutral {{
                    background-color: #e2e3e5;
                    color: #383d41;
                }}
                .sentiment-negative {{
                    background-color: #f8d7da;
                    color: #721c24;
                }}
                .entities {{
                    margin-top: 10px;
                    font-size: 14px;
                    color: #555;
                }}
                .entities-label {{
                    font-weight: bold;
                    color: #333;
                }}
                .no-articles {{
                    color: #666;
                    font-style: italic;
                    padding: 15px;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 40px;
                    padding-top: 20px;
                    border-top: 2px solid #e0e0e0;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 {report_type}</h1>
                    <p class="header-subtitle">MY CUSTOMERS IN NEWS</p>
                </div>
                
                {f'<div class="report-meta">Report generated on {generated_at}</div>' if generated_at else ''}
        """
        
        # Add company sections
        for company_name, company_data in report_data.get('companies', {}).items():
            html += f"""
                <div class="company-section">
                    <div class="company-name">🏢 {company_name}</div>
            """
            
            if company_data.get('articles'):
                for article in company_data['articles']:
                    # Add article URL to the summary if it exists
                    summary = article.get('summary', 'No summary available.')
                    if article.get('url'):
                        summary += f'<br><a href="{article.get("url")}" class="article-link" target="_blank">🔗 Read Full Article</a>'
                    
                    # Format sentiment
                    sentiment = article.get('sentiment', 'neutral').lower()
                    sentiment_class = f"sentiment-{sentiment}"
                    
                    # Format entities if available
                    entities = ""
                    if article.get('entities'):
                        entities = f"""
                        <div class="entities">
                            <span class="entities-label">Key Entities:</span> {article.get('entities')}
                        </div>
                        """
                    
                    html += f"""
                        <div class="article">
                            <div class="article-title">{article.get('title', 'No title')}</div>
                            <div class="article-summary">{summary}</div>
                            <div class="article-meta">
                                <span class="sentiment {sentiment_class}">Sentiment: {article.get('sentiment', 'neutral')}</span>
                            </div>
                            {entities}
                        </div>
                    """
            else:
                html += f"""
                    <div class="no-articles">
                        {company_data.get('message', 'No articles found for this company in the specified timeframe.')}
                    </div>
                """
            
            html += "</div>"  # Close company-section
        
        html += f"""
                <div class="footer">
                    <p><strong>Cprime News Letter</strong></p>
                    <p>Customers in News</p>
                    <p style="margin-top: 15px;">
                        This report contains proprietary market intelligence and strategic analysis.
                        <br>Distribution limited to authorized personnel only.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def create_pdf_newsletter(self, report_data: Dict[str, Any]) -> BytesIO:
        """
        Create PDF version of the newsletter from report data
        
        Args:
            report_data: Structured report data
            
        Returns:
            BytesIO object containing the PDF
        """
        # Create a BytesIO buffer for the PDF
        buffer = BytesIO()
        
        # Create the PDF document
        doc = SimpleDocTemplate(buffer, pagesize=letter,
                                rightMargin=72, leftMargin=72,
                                topMargin=72, bottomMargin=72)
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Add custom styles
        styles.add(ParagraphStyle(
            name='Header1',
            parent=styles['Heading1'],
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#2c5aa0'))
        )
        
        styles.add(ParagraphStyle(
            name='Header2',
            parent=styles['Heading2'],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor('#2c5aa0'))
        )
        
        styles.add(ParagraphStyle(
            name='CompanyName',
            parent=styles['Heading2'],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor('#2c5aa0'),
            borderBottom=1,
            borderColor=colors.HexColor('#e0e0e0'),
            spaceAfter=12
        ))
        
        styles.add(ParagraphStyle(
            name='ArticleTitle',
            parent=styles['Heading3'],
            fontSize=12,
            leading=16,
            spaceAfter=6
        ))
        
        styles.add(ParagraphStyle(
            name='ArticleSummary',
            parent=styles['BodyText'],
            fontSize=10,
            leading=14,
            backColor=colors.HexColor('#f9f9f9'),
            spaceAfter=6
        ))
        
        styles.add(ParagraphStyle(
            name='MetaInfo',
            parent=styles['BodyText'],
            fontSize=9,
            leading=12,
            spaceAfter=6
        ))
        
        # Story will hold all the elements to be added to the document
        story = []
        
        # Format the generated_at timestamp
        generated_at = report_data.get('metadata', {}).get('generated_at', '')
        if generated_at:
            try:
                dt = datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
                generated_at = dt.strftime('%B %d, %Y at %H:%M')
            except:
                generated_at = ""
        
        # Add header
        report_type = report_data.get('metadata', {}).get('report_type', 'CPRIME NEWS DIGEST')
        story.append(Paragraph(report_type, styles['Header1']))
        story.append(Paragraph("MY CUSTOMERS IN NEWS", styles['Header2']))
        
        if generated_at:
            story.append(Paragraph(f"Report generated on {generated_at}", styles['MetaInfo']))
        
        story.append(Spacer(1, 24))
        
        # Add company sections
        for company_name, company_data in report_data.get('companies', {}).items():
            # Add company name
            story.append(Paragraph(f"🏢 {company_name}", styles['CompanyName']))
            
            if company_data.get('articles'):
                for article in company_data['articles']:
                    # Add article title
                    story.append(Paragraph(article.get('title', 'No title'), styles['ArticleTitle']))
                    
                    # Add article summary
                    summary = article.get('summary', 'No summary available.')
                    story.append(Paragraph(summary, styles['ArticleSummary']))
                    
                    # Add article metadata
                    meta = []
                    
                    # Sentiment
                    sentiment = article.get('sentiment', 'neutral')
                    sentiment_style = 'MetaInfo'
                    if sentiment.lower() == 'positive':
                        sentiment_style = 'MetaInfo'
                        sentiment = f"<font color='green'>Sentiment: {sentiment}</font>"
                    elif sentiment.lower() == 'negative':
                        sentiment_style = 'MetaInfo'
                        sentiment = f"<font color='red'>Sentiment: {sentiment}</font>"
                    else:
                        sentiment = f"Sentiment: {sentiment}"
                    
                    meta.append(sentiment)
                    
                    # URL if available
                    if article.get('url'):
                        meta.append(f"URL: {article.get('url')}")
                    
                    # Key entities if available
                    if article.get('entities'):
                        meta.append(f"Key Entities: {article.get('entities')}")
                    
                    story.append(Paragraph("<br/>".join(meta), styles['MetaInfo']))
                    story.append(Spacer(1, 12))
            else:
                story.append(Paragraph(
                    company_data.get('message', 'No articles found for this company in the specified timeframe.'),
                    styles['MetaInfo']
                ))
                story.append(Spacer(1, 12))
            
            story.append(Spacer(1, 24))
        
        # Add footer
        story.append(Spacer(1, 36))
        story.append(Paragraph("<b>Cprime News Letter</b>", styles['MetaInfo']))
        story.append(Paragraph("Customers in News", styles['MetaInfo']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(
            "This report contains proprietary market intelligence and strategic analysis.<br/>" +
            "Distribution limited to authorized personnel only.",
            styles['MetaInfo']
        ))
        
        # Build the PDF
        doc.build(story)
        
        # Reset buffer position to start
        buffer.seek(0)
        return buffer
    
    def send_newsletter(self, recipient_emails: List[str], report_data: Dict[str, Any], 
                   subject: str = None, retries: int = 3) -> bool:
        """
        Send newsletter email to recipients with PDF attachment
        
        Args:
            recipient_emails: List of recipient email addresses
            report_data: Structured report data
            subject: Email subject (optional)
            retries: Number of retry attempts (default: 3)
            
        Returns:
            True if sent successfully, False otherwise
        """
        # Validate recipient emails
        if not recipient_emails or not isinstance(recipient_emails, list):
            print("❌ No valid recipient emails provided")
            return False
            
        # Filter out invalid emails
        valid_emails = []
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        for email in recipient_emails:
            if isinstance(email, str) and re.match(email_regex, email):
                valid_emails.append(email)
        
        if not valid_emails:
            print("❌ No valid email addresses found in recipient list")
            return False
        
        # Create HTML newsletter
        html_content = self.create_html_newsletter(report_data)
        
        # Create subject if not provided
        if not subject:
            metadata = report_data.get('metadata', {})
            date_range = metadata.get('date_range', '')
            
            if date_range:
                try:
                    end_date = date_range.split('to')[-1].strip()
                    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                    date_str = end_dt.strftime('%B %d, %Y')
                except:
                    date_str = datetime.now().strftime('%B %d, %Y')
            else:
                date_str = datetime.now().strftime('%B %d, %Y')
                
            companies_count = metadata.get('companies_analyzed', 0)
            articles_count = metadata.get('total_articles', 0)
            report_type = metadata.get('report_type', 'News Report')
            subject = f"📊 {report_type} - {date_str} "
        
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.sender_email
        message["To"] = ", ".join(valid_emails)
        
        # Add HTML content
        html_part = MIMEText(html_content, "html")
        message.attach(html_part)
        
        # Attempt to send with retries
        last_exception = None
        for attempt in range(retries):
            try:
                # Create PDF newsletter (fresh each attempt in case of file handle issues)
                pdf_buffer = self.create_pdf_newsletter(report_data)
                
                # Add PDF attachment
                pdf_part = MIMEApplication(
                    pdf_buffer.read(),
                    Name="NewsletterReport.pdf"
                )
                pdf_part['Content-Disposition'] = 'attachment; filename="NewsletterReport.pdf"'
                message.attach(pdf_part)
                
                # Close the buffer
                pdf_buffer.close()
                
                # Configure SMTP with timeout
                context = ssl.create_default_context()
                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(self.sender_email, self.password)
                    server.sendmail(self.sender_email, valid_emails, message.as_string())
                
                print(f"✅ Newsletter sent successfully to {len(valid_emails)} recipients with PDF attachment")
                return True
                
            except smtplib.SMTPException as e:
                last_exception = e
                print(f"❌ SMTP error occurred (attempt {attempt + 1}/{retries}): {str(e)}")
                if attempt < retries - 1:
                    import time
                    time.sleep(5 * (attempt + 1))  # Exponential backoff
                    continue
            except ConnectionResetError as e:
                last_exception = e
                print(f"❌ Connection reset by server (attempt {attempt + 1}/{retries}): {str(e)}")
                if attempt < retries - 1:
                    import time
                    time.sleep(5 * (attempt + 1))  # Exponential backoff
                    continue
            except Exception as e:
                last_exception = e
                print(f"❌ Unexpected error occurred (attempt {attempt + 1}/{retries}): {str(e)}")
                if attempt < retries - 1:
                    import time
                    time.sleep(5 * (attempt + 1))  # Exponential backoff
                    continue
        
        print(f"❌ Failed to send newsletter after {retries} attempts")
        if last_exception:
            print(f"Last error: {str(last_exception)}")
        return False