from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo


class RegisterForm(FlaskForm):
    username = StringField("Usuário", validators=[DataRequired(), Length(3, 50)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Senha", validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        "Confirmar senha", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Criar conta")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Senha", validators=[DataRequired()])
    remember = BooleanField("Lembrar de mim")
    submit = SubmitField("Entrar")
