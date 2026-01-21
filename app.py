"""
Staffing Tool - Pilot Application
Flask web app per gestione consulenti, competenze, workload e progetti.
"""

import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash

# Get absolute path for instance folder
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_PATH = os.path.join(BASE_DIR, 'instance')

# Ensure instance folder exists
os.makedirs(INSTANCE_PATH, exist_ok=True)

app = Flask(__name__, instance_path=INSTANCE_PATH)
app.config['SECRET_KEY'] = 'staffing-tool-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(INSTANCE_PATH, "staffing.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy(app)

# =============================================================================
# MODELS
# =============================================================================

class Consultant(db.Model):
    __tablename__ = 'consultant'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    skills = db.relationship('ConsultantSkill', backref='consultant', lazy=True, cascade='all, delete-orphan')
    workloads = db.relationship('MonthlyWorkload', backref='consultant', lazy=True, cascade='all, delete-orphan')
    projects = db.relationship('ConsultantProject', backref='consultant', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Consultant {self.name}>'


class Skill(db.Model):
    __tablename__ = 'skill'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    consultant_skills = db.relationship('ConsultantSkill', backref='skill', lazy=True)

    def __repr__(self):
        return f'<Skill {self.name}>'


class ConsultantSkill(db.Model):
    __tablename__ = 'consultant_skill'
    id = db.Column(db.Integer, primary_key=True)
    consultant_id = db.Column(db.Integer, db.ForeignKey('consultant.id'), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey('skill.id'), nullable=False)
    level = db.Column(db.Integer, nullable=False)  # 1-5

    def __repr__(self):
        return f'<ConsultantSkill {self.consultant_id}-{self.skill_id}: {self.level}>'


class MonthlyWorkload(db.Model):
    __tablename__ = 'monthly_workload'
    id = db.Column(db.Integer, primary_key=True)
    consultant_id = db.Column(db.Integer, db.ForeignKey('consultant.id'), nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    work_days = db.Column(db.Integer, default=0)
    perceived_load = db.Column(db.Integer, default=0)  # 0-10

    def __repr__(self):
        return f'<MonthlyWorkload {self.consultant_id} M{self.month}>'


class Project(db.Model):
    __tablename__ = 'project'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    client = db.Column(db.String(100), nullable=True)
    domain_tags = db.Column(db.String(500), nullable=True)  # comma-separated

    consultant_projects = db.relationship('ConsultantProject', backref='project', lazy=True)

    def __repr__(self):
        return f'<Project {self.name}>'

    def get_tags_list(self):
        """Return tags as a list."""
        if not self.domain_tags:
            return []
        return [t.strip() for t in self.domain_tags.split(',') if t.strip()]


class ConsultantProject(db.Model):
    __tablename__ = 'consultant_project'
    id = db.Column(db.Integer, primary_key=True)
    consultant_id = db.Column(db.Integer, db.ForeignKey('consultant.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    role = db.Column(db.String(100), nullable=True)
    start_month = db.Column(db.Integer, nullable=True)  # 1-12
    start_year = db.Column(db.Integer, nullable=True)
    end_month = db.Column(db.Integer, nullable=True)  # 1-12
    end_year = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    intensity_level = db.Column(db.Integer, nullable=True)  # 1-5

    def __repr__(self):
        return f'<ConsultantProject {self.consultant_id}-{self.project_id}>'

    def get_end_date_sortable(self):
        """Return a sortable tuple for end date, None values sort last."""
        if self.end_year and self.end_month:
            return (self.end_year, self.end_month)
        elif self.end_year:
            return (self.end_year, 12)
        return (0, 0)  # No end date, sort last


# =============================================================================
# SEED DATA
# =============================================================================

BASE_SKILLS = ['Dati', 'PM', 'AI', 'Coraggio civile', 'Empowering']

DEMO_PROJECTS = [
    {'name': 'Internal – AI Adoption Workshop', 'client': 'Internal', 'domain_tags': 'AI, Training'},
    {'name': 'FS – DEI Community', 'client': 'FS', 'domain_tags': 'DEI, Community'},
    {'name': 'Lavazza – Mental Health Day', 'client': 'Lavazza', 'domain_tags': 'Wellbeing, Training'},
]


def seed_base_data():
    """Seed base skills and demo projects if not present."""
    # Seed skills
    for skill_name in BASE_SKILLS:
        existing = Skill.query.filter_by(name=skill_name).first()
        if not existing:
            db.session.add(Skill(name=skill_name))

    # Seed demo projects
    for proj_data in DEMO_PROJECTS:
        existing = Project.query.filter_by(name=proj_data['name']).first()
        if not existing:
            db.session.add(Project(
                name=proj_data['name'],
                client=proj_data['client'],
                domain_tags=proj_data['domain_tags']
            ))

    db.session.commit()


# =============================================================================
# SCORING FUNCTIONS
# =============================================================================

def calculate_workload_score(work_days, perceived_load):
    """
    Calculate workload score and percentages.
    workload_score = work_days + (perceived_load * 0.3)
    max_score = 20 + 10*0.3 = 23
    """
    work_days = max(0, int(work_days or 0))
    perceived_load = max(0, min(10, int(perceived_load or 0)))

    workload_score = work_days + (perceived_load * 0.3)
    max_score = 23.0
    workload_percent = min(100, round(workload_score / max_score * 100))
    availability_percent = 100 - workload_percent

    return {
        'workload_score': round(workload_score, 1),
        'workload_percent': workload_percent,
        'availability_percent': availability_percent,
        'work_days': work_days,
        'perceived_load': perceived_load
    }


def calculate_skill_fit(consultant_skills_dict, required_skills):
    """
    Calculate skill fit score (0-100).
    consultant_skills_dict: {skill_id: level}
    required_skills: [(skill_id, required_level), ...]
    """
    if not required_skills:
        return 100

    per_skill_scores = []
    for skill_id, required_level in required_skills:
        consultant_level = consultant_skills_dict.get(skill_id, 0)
        if required_level > 0:
            score = min(1.0, consultant_level / required_level)
        else:
            score = 1.0 if consultant_level > 0 else 0.0
        per_skill_scores.append(score)

    if per_skill_scores:
        avg_score = sum(per_skill_scores) / len(per_skill_scores)
        return round(avg_score * 100)
    return 0


def normalize_tags(tags_string):
    """Normalize tags to a set of lowercase trimmed strings."""
    if not tags_string:
        return set()
    return set(t.strip().lower() for t in tags_string.split(',') if t.strip())


def calculate_recency_factor(end_year, end_month):
    """
    Calculate recency factor (0.6..1.0).
    <=6 months: 1.0
    7-18: 0.85
    19-36: 0.70
    >36: 0.60
    Missing: 0.75
    """
    if not end_year or not end_month:
        return 0.75

    now = datetime.now()
    end_date = datetime(end_year, end_month, 1)
    months_since = (now.year - end_date.year) * 12 + (now.month - end_date.month)

    if months_since <= 6:
        return 1.0
    elif months_since <= 18:
        return 0.85
    elif months_since <= 36:
        return 0.70
    else:
        return 0.60


def calculate_intensity_factor(intensity_level):
    """
    Calculate intensity factor (0.7..1.0).
    1->0.70, 2->0.80, 3->0.88, 4->0.95, 5->1.00
    Missing: 0.85
    """
    if intensity_level is None:
        return 0.85

    intensity_map = {1: 0.70, 2: 0.80, 3: 0.88, 4: 0.95, 5: 1.00}
    return intensity_map.get(intensity_level, 0.85)


def calculate_project_similarity(consultant_projects, reference_project):
    """
    Calculate project similarity score (0-100) for a consultant.
    Returns (score, best_match_info).
    """
    if not reference_project or not consultant_projects:
        return 0, None

    client_ref = (reference_project.client or '').strip().lower()
    tags_ref = normalize_tags(reference_project.domain_tags)

    best_similarity = 0
    best_match_info = None

    for cp in consultant_projects:
        project = cp.project
        client_past = (project.client or '').strip().lower()
        tags_past = normalize_tags(project.domain_tags)

        # (A) Client match
        client_match = 1 if (client_past and client_ref and client_past == client_ref) else 0

        # (B) Tag overlap
        if tags_ref:
            common_tags = tags_ref & tags_past
            tag_overlap = len(common_tags) / len(tags_ref)
        else:
            tag_overlap = 0

        # (C) Recency factor
        recency = calculate_recency_factor(cp.end_year, cp.end_month)

        # (D) Intensity factor
        intensity_factor = calculate_intensity_factor(cp.intensity_level)

        # Base similarity
        base = 0.45 * tag_overlap + 0.35 * client_match + 0.20 * min(1, tag_overlap + client_match * 0.5)

        # Final per-project similarity
        similarity = max(0, min(1, base * recency * intensity_factor))

        if similarity > best_similarity:
            best_similarity = similarity

            # Recency bucket description
            if not cp.end_year or not cp.end_month:
                recency_desc = "Date non specificate"
            else:
                now = datetime.now()
                end_date = datetime(cp.end_year, cp.end_month, 1)
                months = (now.year - end_date.year) * 12 + (now.month - end_date.month)
                if months <= 6:
                    recency_desc = "Ultimo semestre"
                elif months <= 18:
                    recency_desc = "Ultimo anno e mezzo"
                elif months <= 36:
                    recency_desc = "Ultimi 3 anni"
                else:
                    recency_desc = "Più di 3 anni fa"

            common_tags = tags_ref & tags_past

            best_match_info = {
                'project_name': project.name,
                'project_id': project.id,
                'client_match': client_match == 1,
                'common_tags': len(common_tags),
                'total_ref_tags': len(tags_ref),
                'recency_desc': recency_desc,
                'intensity': cp.intensity_level,
                'role': cp.role
            }

    return round(best_similarity * 100), best_match_info


def calculate_final_score(skill_fit, availability, project_experience=None):
    """
    Calculate final score for match.
    With reference project: 0.55*skill_fit + 0.30*availability + 0.15*project_experience
    Without: 0.65*skill_fit + 0.35*availability
    """
    if project_experience is not None:
        return round(0.55 * skill_fit + 0.30 * availability + 0.15 * project_experience)
    else:
        return round(0.65 * skill_fit + 0.35 * availability)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_consultant_skills_dict(consultant):
    """Get consultant skills as {skill_id: level} dict."""
    return {cs.skill_id: cs.level for cs in consultant.skills}


def get_consultant_workload_for_month(consultant, month):
    """Get workload data for a specific month."""
    workload = MonthlyWorkload.query.filter_by(
        consultant_id=consultant.id,
        month=month
    ).first()

    if workload:
        return calculate_workload_score(workload.work_days, workload.perceived_load)
    return calculate_workload_score(0, 0)


def get_top_skills(consultant, min_level=3, limit=5):
    """Get consultant's top skills (level >= min_level)."""
    skills = []
    for cs in consultant.skills:
        if cs.level >= min_level:
            skills.append({
                'name': cs.skill.name,
                'level': cs.level
            })
    skills.sort(key=lambda x: x['level'], reverse=True)
    return skills[:limit]


def get_recent_projects(consultant, limit=2):
    """Get consultant's most recent projects."""
    projects = []
    for cp in consultant.projects:
        projects.append({
            'id': cp.project.id,
            'name': cp.project.name,
            'role': cp.role,
            'end_year': cp.end_year,
            'end_month': cp.end_month,
            'sort_key': cp.get_end_date_sortable()
        })
    projects.sort(key=lambda x: x['sort_key'], reverse=True)
    return projects[:limit]


def safe_int(value, default=0, min_val=None, max_val=None):
    """Safely convert to int with optional clamping."""
    try:
        result = int(value)
    except (ValueError, TypeError):
        result = default

    if min_val is not None:
        result = max(min_val, result)
    if max_val is not None:
        result = min(max_val, result)

    return result


def get_month_name(month_num):
    """Get Italian month name."""
    months = {
        1: 'Gennaio', 2: 'Febbraio', 3: 'Marzo', 4: 'Aprile',
        5: 'Maggio', 6: 'Giugno', 7: 'Luglio', 8: 'Agosto',
        9: 'Settembre', 10: 'Ottobre', 11: 'Novembre', 12: 'Dicembre'
    }
    return months.get(month_num, str(month_num))


# Make helper available in templates
app.jinja_env.globals['get_month_name'] = get_month_name


# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def index():
    """Home page with navigation buttons."""
    return render_template('index.html')


@app.route('/inserisci', methods=['GET', 'POST'])
def inserisci():
    """Consultant insert/update page."""
    if request.method == 'POST':
        consultant_id = request.form.get('consultant_id')
        consultant_name = request.form.get('consultant_name', '').strip()

        if not consultant_name:
            flash('Il nome del consulente è obbligatorio.', 'error')
            return redirect(url_for('inserisci'))

        # Create or update consultant
        if consultant_id and consultant_id != 'new':
            consultant = Consultant.query.get(int(consultant_id))
            if not consultant:
                flash('Consulente non trovato.', 'error')
                return redirect(url_for('inserisci'))
            consultant.name = consultant_name
        else:
            consultant = Consultant(name=consultant_name)
            db.session.add(consultant)
            db.session.flush()  # Get the ID

        # Handle new skill creation
        new_skill_name = request.form.get('new_skill_name', '').strip()
        new_skill_level = safe_int(request.form.get('new_skill_level'), 0, 0, 5)

        if new_skill_name:
            existing_skill = Skill.query.filter_by(name=new_skill_name).first()
            if not existing_skill:
                existing_skill = Skill(name=new_skill_name)
                db.session.add(existing_skill)
                db.session.flush()

            if new_skill_level >= 1:
                # Add or update consultant skill
                cs = ConsultantSkill.query.filter_by(
                    consultant_id=consultant.id,
                    skill_id=existing_skill.id
                ).first()
                if cs:
                    cs.level = new_skill_level
                else:
                    db.session.add(ConsultantSkill(
                        consultant_id=consultant.id,
                        skill_id=existing_skill.id,
                        level=new_skill_level
                    ))

        # Update skills
        all_skills = Skill.query.all()
        for skill in all_skills:
            level_key = f'skill_level_{skill.id}'
            level = safe_int(request.form.get(level_key), 0, 0, 5)

            existing_cs = ConsultantSkill.query.filter_by(
                consultant_id=consultant.id,
                skill_id=skill.id
            ).first()

            if level >= 1:
                if existing_cs:
                    existing_cs.level = level
                else:
                    db.session.add(ConsultantSkill(
                        consultant_id=consultant.id,
                        skill_id=skill.id,
                        level=level
                    ))
            else:
                # Remove skill if level is 0 or empty
                if existing_cs:
                    db.session.delete(existing_cs)

        # Update monthly workload
        for month in range(1, 13):
            work_days = safe_int(request.form.get(f'work_days_{month}'), 0, 0)
            perceived = safe_int(request.form.get(f'perceived_{month}'), 0, 0, 10)

            existing_wl = MonthlyWorkload.query.filter_by(
                consultant_id=consultant.id,
                month=month
            ).first()

            if existing_wl:
                existing_wl.work_days = work_days
                existing_wl.perceived_load = perceived
            else:
                db.session.add(MonthlyWorkload(
                    consultant_id=consultant.id,
                    month=month,
                    work_days=work_days,
                    perceived_load=perceived
                ))

        # Handle new project creation
        new_project_name = request.form.get('new_project_name', '').strip()
        new_project_client = request.form.get('new_project_client', '').strip()
        new_project_tags = request.form.get('new_project_tags', '').strip()

        new_project = None
        if new_project_name:
            existing_proj = Project.query.filter_by(name=new_project_name).first()
            if not existing_proj:
                new_project = Project(
                    name=new_project_name,
                    client=new_project_client,
                    domain_tags=new_project_tags
                )
                db.session.add(new_project)
                db.session.flush()
            else:
                new_project = existing_proj

        # Handle project experiences (multiple rows)
        exp_count = safe_int(request.form.get('exp_count'), 0)
        for i in range(exp_count + 1):  # +1 for potential new project experience
            prefix = f'exp_{i}_'
            project_id = request.form.get(f'{prefix}project_id')

            # Check if this is the new project row
            if i == exp_count and new_project:
                project_id = str(new_project.id)

            if not project_id or project_id == '':
                continue

            project_id = safe_int(project_id, 0)
            if project_id <= 0:
                continue

            role = request.form.get(f'{prefix}role', '').strip()
            start_month = safe_int(request.form.get(f'{prefix}start_month'), None)
            start_year = safe_int(request.form.get(f'{prefix}start_year'), None)
            end_month = safe_int(request.form.get(f'{prefix}end_month'), None)
            end_year = safe_int(request.form.get(f'{prefix}end_year'), None)
            intensity = safe_int(request.form.get(f'{prefix}intensity'), None)
            notes = request.form.get(f'{prefix}notes', '').strip()

            # Validate months
            if start_month is not None and (start_month < 1 or start_month > 12):
                start_month = None
            if end_month is not None and (end_month < 1 or end_month > 12):
                end_month = None
            if intensity is not None and (intensity < 1 or intensity > 5):
                intensity = None

            db.session.add(ConsultantProject(
                consultant_id=consultant.id,
                project_id=project_id,
                role=role if role else None,
                start_month=start_month,
                start_year=start_year,
                end_month=end_month,
                end_year=end_year,
                intensity_level=intensity,
                notes=notes if notes else None
            ))

        db.session.commit()
        flash(f'Consulente "{consultant_name}" salvato con successo!', 'success')
        return redirect(url_for('inserisci'))

    # GET request
    consultants = Consultant.query.order_by(Consultant.name).all()
    skills = Skill.query.order_by(Skill.name).all()
    projects = Project.query.order_by(Project.name).all()

    selected_id = request.args.get('selected')
    selected_consultant = None
    consultant_skills = {}
    consultant_workloads = {}

    if selected_id and selected_id != 'new':
        selected_consultant = Consultant.query.get(int(selected_id))
        if selected_consultant:
            consultant_skills = {cs.skill_id: cs.level for cs in selected_consultant.skills}
            for wl in selected_consultant.workloads:
                consultant_workloads[wl.month] = {
                    'work_days': wl.work_days,
                    'perceived_load': wl.perceived_load
                }

    # Prepare consultants list with details
    consultants_list = []
    for c in consultants:
        consultants_list.append({
            'id': c.id,
            'name': c.name,
            'top_skills': get_top_skills(c),
            'recent_projects': get_recent_projects(c)
        })

    return render_template('inserisci.html',
                          consultants=consultants,
                          skills=skills,
                          projects=projects,
                          selected_consultant=selected_consultant,
                          consultant_skills=consultant_skills,
                          consultant_workloads=consultant_workloads,
                          consultants_list=consultants_list)


@app.route('/consultant/<int:consultant_id>')
def consultant_profile(consultant_id):
    """Consultant profile page."""
    consultant = Consultant.query.get_or_404(consultant_id)

    # Skills sorted by level desc
    skills = []
    for cs in consultant.skills:
        skills.append({
            'name': cs.skill.name,
            'level': cs.level
        })
    skills.sort(key=lambda x: x['level'], reverse=True)

    # Workloads
    workloads = []
    for month in range(1, 13):
        wl = MonthlyWorkload.query.filter_by(
            consultant_id=consultant.id,
            month=month
        ).first()

        if wl:
            score_data = calculate_workload_score(wl.work_days, wl.perceived_load)
        else:
            score_data = calculate_workload_score(0, 0)

        workloads.append({
            'month': month,
            'month_name': get_month_name(month),
            **score_data
        })

    # Projects sorted by end date desc
    projects = []
    for cp in consultant.projects:
        projects.append({
            'id': cp.project.id,
            'name': cp.project.name,
            'client': cp.project.client,
            'role': cp.role,
            'start_month': cp.start_month,
            'start_year': cp.start_year,
            'end_month': cp.end_month,
            'end_year': cp.end_year,
            'intensity': cp.intensity_level,
            'notes': cp.notes,
            'sort_key': cp.get_end_date_sortable()
        })
    projects.sort(key=lambda x: x['sort_key'], reverse=True)

    # Chart data for workload
    chart_data = json.dumps({
        'labels': [w['month_name'] for w in workloads],
        'workload': [w['workload_percent'] for w in workloads],
        'availability': [w['availability_percent'] for w in workloads]
    })

    return render_template('consultant.html',
                          consultant=consultant,
                          skills=skills,
                          workloads=workloads,
                          projects=projects,
                          chart_data=chart_data)


@app.route('/consultant/<int:consultant_id>/delete', methods=['POST'])
def delete_consultant(consultant_id):
    """Delete a consultant."""
    consultant = Consultant.query.get_or_404(consultant_id)
    name = consultant.name
    db.session.delete(consultant)
    db.session.commit()
    flash(f'Consulente "{name}" eliminato.', 'success')
    return redirect(url_for('inserisci'))


@app.route('/projects', methods=['GET', 'POST'])
def projects():
    """Projects catalog page."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        client = request.form.get('client', '').strip()
        domain_tags = request.form.get('domain_tags', '').strip()

        if not name:
            flash('Il nome del progetto è obbligatorio.', 'error')
            return redirect(url_for('projects'))

        existing = Project.query.filter_by(name=name).first()
        if existing:
            flash('Esiste già un progetto con questo nome.', 'error')
            return redirect(url_for('projects'))

        project = Project(name=name, client=client, domain_tags=domain_tags)
        db.session.add(project)
        db.session.commit()
        flash(f'Progetto "{name}" creato con successo!', 'success')
        return redirect(url_for('projects'))

    # Filters
    search = request.args.get('search', '').strip()
    client_filter = request.args.get('client', '').strip()
    tag_filter = request.args.get('tag', '').strip()

    query = Project.query

    if search:
        query = query.filter(Project.name.ilike(f'%{search}%'))
    if client_filter:
        query = query.filter(Project.client.ilike(f'%{client_filter}%'))
    if tag_filter:
        query = query.filter(Project.domain_tags.ilike(f'%{tag_filter}%'))

    all_projects = query.order_by(Project.name).all()

    # Get unique clients and tags for filters
    all_clients = set()
    all_tags = set()
    for p in Project.query.all():
        if p.client:
            all_clients.add(p.client)
        for tag in p.get_tags_list():
            all_tags.add(tag)

    # Prepare projects with consultants who worked on them
    projects_list = []
    for p in all_projects:
        consultants_on_project = []
        for cp in p.consultant_projects:
            consultants_on_project.append({
                'id': cp.consultant.id,
                'name': cp.consultant.name,
                'role': cp.role
            })

        projects_list.append({
            'id': p.id,
            'name': p.name,
            'client': p.client,
            'tags': p.get_tags_list(),
            'consultants': consultants_on_project
        })

    return render_template('projects.html',
                          projects=projects_list,
                          all_clients=sorted(all_clients),
                          all_tags=sorted(all_tags),
                          search=search,
                          client_filter=client_filter,
                          tag_filter=tag_filter)


@app.route('/overview')
def overview():
    """Account workload overview page."""
    # Get filter parameters
    month = safe_int(request.args.get('month'), datetime.now().month, 1, 12)
    search = request.args.get('search', '').strip()
    skill_id = safe_int(request.args.get('skill_id'), 0)
    min_level = safe_int(request.args.get('min_level'), 1, 1, 5)
    project_id = safe_int(request.args.get('project_id'), 0)
    client_filter = request.args.get('client', '').strip()
    tag_filter = request.args.get('tag', '').strip()
    view = request.args.get('view', 'cards')

    # Start with all consultants
    query = Consultant.query

    if search:
        query = query.filter(Consultant.name.ilike(f'%{search}%'))

    consultants = query.order_by(Consultant.name).all()

    # Apply filters and calculate data
    results = []
    for c in consultants:
        # Skill filter
        if skill_id > 0:
            cs = ConsultantSkill.query.filter_by(
                consultant_id=c.id,
                skill_id=skill_id
            ).first()
            if not cs or cs.level < min_level:
                continue

        # Project filter
        if project_id > 0:
            has_project = ConsultantProject.query.filter_by(
                consultant_id=c.id,
                project_id=project_id
            ).first()
            if not has_project:
                continue

        # Client filter
        if client_filter:
            has_client = False
            for cp in c.projects:
                if cp.project.client and cp.project.client.lower() == client_filter.lower():
                    has_client = True
                    break
            if not has_client:
                continue

        # Tag filter
        if tag_filter:
            has_tag = False
            tag_lower = tag_filter.lower()
            for cp in c.projects:
                for t in cp.project.get_tags_list():
                    if t.lower() == tag_lower:
                        has_tag = True
                        break
                if has_tag:
                    break
            if not has_tag:
                continue

        # Calculate workload
        workload_data = get_consultant_workload_for_month(c, month)

        # Get skill level for selected skill (for chart Y axis)
        skill_level = 0
        if skill_id > 0:
            cs = ConsultantSkill.query.filter_by(
                consultant_id=c.id,
                skill_id=skill_id
            ).first()
            if cs:
                skill_level = cs.level
        else:
            # Average of top 3 skills
            top = get_top_skills(c, min_level=1, limit=3)
            if top:
                skill_level = round(sum(s['level'] for s in top) / len(top), 1)

        results.append({
            'id': c.id,
            'name': c.name,
            'workload_data': workload_data,
            'top_skills': get_top_skills(c),
            'recent_projects': get_recent_projects(c),
            'skill_level': skill_level
        })

    # Sort by lowest workload (highest availability)
    results.sort(key=lambda x: x['workload_data']['workload_percent'])

    # Prepare chart data
    chart_data = json.dumps({
        'consultants': [
            {
                'id': r['id'],
                'name': r['name'],
                'workload': r['workload_data']['workload_percent'],
                'availability': r['workload_data']['availability_percent'],
                'skill_level': r['skill_level'],
                'projects': [p['name'] for p in r['recent_projects']]
            }
            for r in results
        ]
    })

    # Get all skills, projects, clients, tags for filter dropdowns
    all_skills = Skill.query.order_by(Skill.name).all()
    all_projects = Project.query.order_by(Project.name).all()

    all_clients = set()
    all_tags = set()
    for p in all_projects:
        if p.client:
            all_clients.add(p.client)
        for t in p.get_tags_list():
            all_tags.add(t)

    selected_skill = Skill.query.get(skill_id) if skill_id > 0 else None

    return render_template('overview.html',
                          results=results,
                          month=month,
                          search=search,
                          skill_id=skill_id,
                          min_level=min_level,
                          project_id=project_id,
                          client_filter=client_filter,
                          tag_filter=tag_filter,
                          view=view,
                          all_skills=all_skills,
                          all_projects=all_projects,
                          all_clients=sorted(all_clients),
                          all_tags=sorted(all_tags),
                          selected_skill=selected_skill,
                          chart_data=chart_data)


@app.route('/match', methods=['GET', 'POST'])
def match():
    """Project match page."""
    all_skills = Skill.query.order_by(Skill.name).all()
    all_projects = Project.query.order_by(Project.name).all()

    results = []
    chart_data = json.dumps({'consultants': []})

    # Form state
    month = safe_int(request.args.get('month') or request.form.get('month'),
                     datetime.now().month, 1, 12)
    selected_skill_ids = request.form.getlist('skill_ids') if request.method == 'POST' else []
    reference_project_id = safe_int(request.form.get('reference_project_id'), 0)
    project_days = request.form.get('project_days', '')

    # Get required levels for each skill
    required_skills = []
    skill_levels = {}
    for skill in all_skills:
        level_key = f'skill_level_{skill.id}'
        level = safe_int(request.form.get(level_key), 3, 1, 5)
        skill_levels[skill.id] = level
        if str(skill.id) in selected_skill_ids:
            required_skills.append((skill.id, level))

    reference_project = None
    if reference_project_id > 0:
        reference_project = Project.query.get(reference_project_id)

    if request.method == 'POST':
        consultants = Consultant.query.all()

        for c in consultants:
            # Calculate skill fit
            c_skills = get_consultant_skills_dict(c)
            skill_fit = calculate_skill_fit(c_skills, required_skills)

            # Calculate availability
            workload_data = get_consultant_workload_for_month(c, month)
            availability = workload_data['availability_percent']

            # Calculate project similarity if reference project selected
            project_experience = None
            best_match_info = None
            if reference_project:
                project_experience, best_match_info = calculate_project_similarity(
                    c.projects, reference_project
                )

            # Calculate final score
            final = calculate_final_score(skill_fit, availability, project_experience)

            # Skill breakdown
            skill_breakdown = []
            for skill_id, req_level in required_skills:
                skill = Skill.query.get(skill_id)
                consultant_level = c_skills.get(skill_id, 0)
                skill_breakdown.append({
                    'name': skill.name,
                    'consultant_level': consultant_level,
                    'required_level': req_level,
                    'met': consultant_level >= req_level
                })

            results.append({
                'id': c.id,
                'name': c.name,
                'final_score': final,
                'skill_fit': skill_fit,
                'availability': availability,
                'project_experience': project_experience,
                'best_match_info': best_match_info,
                'skill_breakdown': skill_breakdown,
                'workload_data': workload_data,
                'top_skills': get_top_skills(c),
                'recent_projects': get_recent_projects(c)
            })

        # Sort by final score desc
        results.sort(key=lambda x: x['final_score'], reverse=True)

        # Prepare chart data
        chart_data = json.dumps({
            'consultants': [
                {
                    'id': r['id'],
                    'name': r['name'],
                    'availability': r['availability'],
                    'skill_fit': r['skill_fit'],
                    'project_experience': r['project_experience'] if r['project_experience'] is not None else 0,
                    'final_score': r['final_score'],
                    'best_match': r['best_match_info']['project_name'] if r['best_match_info'] else None
                }
                for r in results
            ]
        })

    view = request.args.get('view', 'cards')

    return render_template('match.html',
                          results=results,
                          month=month,
                          all_skills=all_skills,
                          all_projects=all_projects,
                          selected_skill_ids=selected_skill_ids,
                          skill_levels=skill_levels,
                          reference_project_id=reference_project_id,
                          reference_project=reference_project,
                          project_days=project_days,
                          chart_data=chart_data,
                          view=view)


@app.route('/admin/reset-db', methods=['GET', 'POST'])
def admin_reset_db():
    """Admin reset database page."""
    if request.method == 'POST':
        # Drop all tables and recreate
        db.drop_all()
        db.create_all()
        seed_base_data()
        flash('Database resettato e dati base ricreati con successo!', 'success')
        return redirect(url_for('index'))

    return render_template('admin_reset.html')


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_base_data()

    app.run(debug=True, port=5000)
