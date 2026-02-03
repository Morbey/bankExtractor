"""Email sender for report delivery."""

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from src.core import CredentialManager, get_logger

from .formatters import HTMLFormatter
from .models import ReportData

logger = get_logger("reporter.mailer")


class ReportMailer:
    """Sends reports via email to accountants or recipients."""

    # SMTP server configurations
    SMTP_SERVERS = {
        "gmail": {
            "host": "smtp.gmail.com",
            "port": 587,
            "use_tls": True,
        },
        "hotmail": {
            "host": "smtp.office365.com",
            "port": 587,
            "use_tls": True,
        },
        "outlook": {
            "host": "smtp.office365.com",
            "port": 587,
            "use_tls": True,
        },
    }

    def __init__(self, provider: str = "gmail"):
        """Initialize the mailer.

        Args:
            provider: Email provider to use (gmail, hotmail, outlook)
        """
        self.logger = logger
        self.provider = provider.lower()

        if self.provider not in self.SMTP_SERVERS:
            raise ValueError(f"Provider desconhecido: {provider}")

        self.smtp_config = self.SMTP_SERVERS[self.provider]

    def send_report(
        self,
        report: ReportData,
        recipient_email: str,
        attachments: Optional[list[Path]] = None,
        subject: Optional[str] = None,
    ) -> bool:
        """Send a report via email.

        Args:
            report: ReportData to send
            recipient_email: Email address of the recipient
            attachments: Optional list of file paths to attach
            subject: Optional custom subject line

        Returns:
            True if sent successfully, False otherwise
        """
        # Get credentials
        sender_email, password = self._get_credentials()
        if not sender_email or not password:
            self.logger.error("Credenciais de email não configuradas.")
            return False

        # Build subject
        if not subject:
            subject = f"Relatório Financeiro - {report.period_name}"

        # Build email
        msg = MIMEMultipart("mixed")
        msg["From"] = sender_email
        msg["To"] = recipient_email
        msg["Subject"] = subject

        # Create HTML body
        html_formatter = HTMLFormatter()
        html_content = html_formatter.format(report)

        # Create alternative part for HTML/plain text
        alt_part = MIMEMultipart("alternative")

        # Plain text version
        plain_text = self._create_plain_text(report)
        alt_part.attach(MIMEText(plain_text, "plain", "utf-8"))

        # HTML version
        alt_part.attach(MIMEText(html_content, "html", "utf-8"))

        msg.attach(alt_part)

        # Add attachments
        if attachments:
            for file_path in attachments:
                if file_path.exists():
                    self._attach_file(msg, file_path)

        # Send email
        try:
            self.logger.info(f"A enviar relatório para {recipient_email}...")

            with smtplib.SMTP(self.smtp_config["host"], self.smtp_config["port"]) as server:
                if self.smtp_config["use_tls"]:
                    server.starttls()
                server.login(sender_email, password)
                server.send_message(msg)

            self.logger.info("Relatório enviado com sucesso!")
            return True

        except smtplib.SMTPAuthenticationError:
            self.logger.error(
                "Erro de autenticação. Verifique as credenciais ou use uma App Password."
            )
            return False
        except smtplib.SMTPException as e:
            self.logger.error(f"Erro SMTP: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Erro ao enviar email: {e}")
            return False

    def _get_credentials(self) -> tuple[Optional[str], Optional[str]]:
        """Get email credentials for sending."""
        try:
            email = CredentialManager.get_or_prompt(
                self.provider,
                "email",
                f"Email {self.provider}",
                password=False,
            )
            password = CredentialManager.get_or_prompt(
                self.provider,
                "password",
                f"Password/App Password {self.provider}",
                password=True,
            )
            return email, password
        except Exception as e:
            self.logger.error(f"Erro ao obter credenciais: {e}")
            return None, None

    def _create_plain_text(self, report: ReportData) -> str:
        """Create plain text version of the report."""
        lines = [
            f"RELATÓRIO FINANCEIRO - {report.period_name}",
            "=" * 50,
            "",
            "RESUMO",
            "-" * 20,
            f"Período: {report.period_start} a {report.period_end}",
            f"Total documentos: {report.total_documents}",
            f"Faturas: {report.total_invoices}",
            f"Extratos: {report.total_statements}",
            f"Recibos: {report.total_receipts}",
            "",
            f"TOTAL: {report.total_amount:.2f}€",
            "",
        ]

        # Comparison
        if report.comparison:
            comp = report.comparison
            lines.extend(
                [
                    "COMPARAÇÃO COM MÊS ANTERIOR",
                    "-" * 20,
                    f"Mês anterior: {comp.previous_total:.2f}€",
                    f"Mês atual: {comp.current_total:.2f}€",
                    f"Diferença: {comp.difference:+.2f}€ ({comp.percentage_change:+.1f}%)",
                    "",
                ]
            )

        # Categories
        if report.by_category:
            lines.extend(
                [
                    "DESPESAS POR CATEGORIA",
                    "-" * 20,
                ]
            )
            for cat in report.by_category:
                lines.append(f"  {cat.name}: {cat.amount:.2f}€ ({cat.percentage:.1f}%)")
            lines.append("")

        # Providers
        if report.by_provider:
            lines.extend(
                [
                    "TOP FORNECEDORES",
                    "-" * 20,
                ]
            )
            for prov in report.by_provider[:10]:
                lines.append(
                    f"  {prov.name}: {prov.total_amount:.2f}€ ({prov.document_count} docs)"
                )
            lines.append("")

        lines.extend(
            [
                "-" * 50,
                f"Relatório gerado em {report.generated_at}",
                "Bank Extractor - Gestor Financeiro Pessoal",
            ]
        )

        return "\n".join(lines)

    def _attach_file(self, msg: MIMEMultipart, file_path: Path) -> None:
        """Attach a file to the email message."""
        try:
            with open(file_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=file_path.name)
            part["Content-Disposition"] = f'attachment; filename="{file_path.name}"'
            msg.attach(part)
            self.logger.debug(f"Anexado: {file_path.name}")
        except Exception as e:
            self.logger.warning(f"Não foi possível anexar {file_path}: {e}")

    def send_documents_package(
        self,
        report: ReportData,
        recipient_email: str,
        document_paths: list[Path],
        subject: Optional[str] = None,
    ) -> bool:
        """Send report with all related documents as attachments.

        Args:
            report: ReportData to send
            recipient_email: Email address of the recipient
            document_paths: List of document paths to attach
            subject: Optional custom subject line

        Returns:
            True if sent successfully
        """
        if not subject:
            subject = f"Documentação Financeira - {report.period_name}"

        return self.send_report(
            report=report,
            recipient_email=recipient_email,
            attachments=document_paths,
            subject=subject,
        )
