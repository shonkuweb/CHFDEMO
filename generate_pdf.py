from markdown_pdf import MarkdownPdf
from markdown_pdf.section import Section

pdf = MarkdownPdf(toc_level=2)

with open('CHF_Project_Handover_Report.md', 'r', encoding='utf-8') as f:
    text = f.read()

pdf.add_section(Section(text))

pdf.meta["title"] = "CHF Botanical Luxury - Project Handover"
pdf.meta["author"] = "Team ShonkuWeb"

pdf.save('CHF_Project_Handover_Report.pdf')
print("PDF successfully generated.")
