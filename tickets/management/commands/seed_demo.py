import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from tickets.models import Category, Ticket, Comment
from tickets.services import audit
from kb.models import Article
User = get_user_model()

class Command(BaseCommand):
    help = "Create repeatable demo users, tickets, comments and knowledge articles."
    def handle(self, *args, **options):
        random.seed(41)
        users = {}
        demo = [
            ("admin@demo.com", "Demo Admin", "admin"),
            ("tech@demo.com", "Demo Technician", "technician"),
            ("tech2@demo.com", "Second Technician", "technician"),
            ("employee@demo.com", "Demo Employee", "employee"),
            ("employee2@demo.com", "Amaka Okafor", "employee"),
            ("employee3@demo.com", "Chinedu Eze", "employee"),
        ]
        for email, name, role in demo:
            username = email.split("@")[0]
            user, created = User.objects.get_or_create(email=email, defaults={"username": username, "first_name": name.split()[0], "last_name": " ".join(name.split()[1:]), "role": role, "is_staff": role == "admin"})
            if created: user.set_password("DemoPass123!"); user.save()
            users[email] = user
        category_data = [("Hardware", "hardware"), ("Network", "network"), ("Software", "software"), ("Accounts", "accounts")]
        categories = [Category.objects.get_or_create(name=n, slug=s)[0] for n, s in category_data]
        titles = ["Laptop will not connect to office Wi-Fi", "MFA prompt loops during sign-in", "Printer queue stuck on pending", "Request access to shared finance folder", "VPN disconnects after a few minutes", "Outlook search returns no results", "New starter needs a workstation", "Laptop battery drains unusually fast", "Cannot install approved application", "Password reset link has expired", "Video calls have intermittent audio", "External monitor is not detected", "Shared mailbox access request", "Browser crashes when opening portal", "Desktop is running very slowly"]
        descriptions = ["The issue started this morning and is affecting normal work. I have restarted the device and checked the cable/network connection where applicable.", "Please investigate and advise on the recommended fix. This is affecting my day-to-day work.", "I have tried signing out and back in but the problem persists. No recent changes were made by me."]
        employees = [users[x] for x in ("employee@demo.com", "employee2@demo.com", "employee3@demo.com")]
        techs = [users[x] for x in ("tech@demo.com", "tech2@demo.com")]
        existing = Ticket.objects.count()
        for i in range(existing, 30):
            category = categories[i % len(categories)]
            status = ["open", "in_progress", "resolved", "closed"][i % 4]
            created_delta = timedelta(hours=random.randint(1, 240), days=random.randint(0, 12))
            created_at = timezone.now() - created_delta
            ticket = Ticket.objects.create(title=f"{titles[i % len(titles)]} #{i+1}", description=random.choice(descriptions), category=category, priority=random.choice(["low", "medium", "high", "critical"]), status=status, requester=random.choice(employees), assignee=random.choice(techs) if i % 4 else None)
            Ticket.objects.filter(pk=ticket.pk).update(created_at=created_at, updated_at=created_at)
            if status in {"resolved", "closed"}:
                Ticket.objects.filter(pk=ticket.pk).update(resolved_at=created_at + timedelta(hours=random.randint(1, 18)))
            ticket.refresh_from_db()
            audit(ticket, users["admin@demo.com"], "seeded_demo_ticket", {"status": status})
            Comment.objects.create(ticket=ticket, author=ticket.requester, body="Additional context: this is blocking a routine work task. Thank you for looking into it.")
            if ticket.assignee: Comment.objects.create(ticket=ticket, author=ticket.assignee, body="I am investigating this issue and will update the ticket with findings.")
        articles = [
            ("Troubleshoot common Wi-Fi connection issues", "A quick checklist for office wireless problems.", "Confirm Wi-Fi is enabled, reconnect to the approved SSID, forget and rejoin the network, then check whether other devices are affected. Escalate recurring access point issues to the network team.", "network"),
            ("Safe password reset and MFA recovery", "Steps for recovering access without sharing credentials.", "Verify the requester using the approved identity process. Use the approved password reset workflow, never ask for a password in chat, and re-enrol MFA only after identity verification. Record the action in the ticket.", "accounts"),
            ("First steps for a slow Windows workstation", "A safe first-line performance checklist.", "Check available disk space, restart if appropriate, close unused applications, review Task Manager for unusual CPU or memory use, and confirm updates are not in progress. Collect device details before escalation.", "software"),
            ("Printer queue stuck on pending", "Resolve common print queue issues.", "Confirm the correct printer is selected and reachable. Cancel only the affected user's stuck jobs, check printer status, and restart the approved print spooler service if policy allows. Escalate repeated errors with the printer name and error message.", "hardware"),
        ]
        for title, summary, content, slug in articles:
            Article.objects.get_or_create(title=title, defaults={"summary": summary, "content": content, "category": Category.objects.get(slug=slug), "author": users["tech@demo.com"], "published": True})
        self.stdout.write(self.style.SUCCESS("Demo data ready. Demo password for all seeded users: DemoPass123!"))
