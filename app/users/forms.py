from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Optional

from app.services.classes import CLASSES

# Curated FontAwesome icon avatars — deliberately NOT a free-form image
# upload. No storage/moderation pipeline needed and no way for a player
# to put an image that violates the terms of service into someone else's
# browser, while still giving a real choice of identity.
AVATAR_CHOICES = [
    ("fa-user-shield", "Guardião"),
    ("fa-hat-wizard", "Mago"),
    ("fa-dragon", "Dragão"),
    ("fa-khanda", "Espadachim"),
    ("fa-shield-halved", "Escudeiro"),
    ("fa-cat", "Felino"),
    ("fa-dove", "Mensageiro"),
    ("fa-ghost", "Fantasma"),
    ("fa-chess-knight", "Cavaleiro"),
    ("fa-spider", "Aracnídeo"),
    ("fa-skull", "Caveira"),
    ("fa-paw", "Fera"),
]

VALID_AVATAR_KEYS = {key for key, _ in AVATAR_CHOICES}


class ProfileForm(FlaskForm):
    display_name = StringField("Nome de exibição", validators=[DataRequired(), Length(1, 60)])
    avatar_key = SelectField("Avatar", choices=AVATAR_CHOICES, validators=[DataRequired()])
    bio = TextAreaField("Bio", validators=[Optional(), Length(max=280)])
    submit = SubmitField("Salvar")


CLASS_CHOICES = [(key, cls["name"]) for key, cls in CLASSES.items()]


class ClassForm(FlaskForm):
    character_class = SelectField("Classe", choices=CLASS_CHOICES, validators=[DataRequired()])
    submit = SubmitField("Confirmar")
