import secrets
import os
from PIL import Image
from app import app, db, bcrypt, mail
from flask import render_template, request, make_response, redirect, session, url_for, send_file, flash, abort
from hashlib import sha256
from app.forms import RegistrationForm, LoginForm, UpdateAccountForm, PostForm, RequestResetForm, ResetPasswordForm
from app.token import generate_confirmation_token, confirm_token
from app.email import send_email
from app.models import User, Post
from flask_login import login_user, current_user, logout_user, login_required


@app.route("/index")
@app.route("/home")
@app.route("/")
def home():
    return render_template('home.html')


@app.route("/files/license")
def license():
    return render_template('license.html')


@app.route("/files/disclaimer")
def disclaimer():
    return render_template('disclaimer.html')


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    f_name, f_ext = os.path.splitext(form_picture.filename)
    picture_filename = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/img', picture_filename)

    output_size = (125, 125)
    image = Image.open(form_picture)
    image.thumbnail(output_size)
    image.save(picture_path)

    return picture_filename


@app.route('/news')
def news():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(
        Post.date_posted.desc()).paginate(
        page=page, per_page=5)

    return render_template('news.html', posts=posts)


'''
Forms
'''


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(
            sha256(
                (form.password.data +
                 form.email.data +
                 app.config['SECURITY_PASSWORD_SALT']).encode()).hexdigest()).decode('utf-8')

        user = User(
            username=form.username.data,
            email=form.email.data,
            password=hashed_password)

        db.session.add(user)
        db.session.commit()

        token = generate_confirmation_token(form.email.data)

        confirmation_url = url_for('confirm', token=token, _external=True)
        subject = 'Please confirm your email'
        html = render_template('activation.html', url=confirmation_url)

        send_email(form.email.data, subject, html)

        flash(f'Account created for {form.username.data}! Confirmation email sent to {form.email.data}.', 'success')

        return redirect(url_for('home'))

    return render_template('register.html', form=form)


@app.route('/confirm/<token>', methods=['GET', 'POST'])
def confirm(token):

    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        email = confirm_token(token) == form.email.data

        if user.confirmed:
            flash('Account already confirmed. Please login.', 'info')

        if user and email and bcrypt.check_password_hash(user.password, sha256(
                (form.password.data + form.email.data + app.config['SECURITY_PASSWORD_SALT']).encode()).hexdigest()):

            user.confirmed = True

            db.session.add(user)
            db.session.commit()

            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')

            return redirect(next_page) if next_page else redirect(
                url_for('home'))

        else:
            flash('Activation Unsuccessful. Please check email and password', 'danger')

    return render_template('login.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        confirm = user.confirmed == True
        confirmed = ''
        if confirm == False:
            confirmed = ' and check to make sure you have activated your account'

        if user and confirm and bcrypt.check_password_hash(user.password, sha256(
                (form.password.data + form.email.data + app.config['SECURITY_PASSWORD_SALT']).encode()).hexdigest()):

            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')

            flash(f'Logged in successfully.', 'success')
            return redirect(next_page) if next_page else redirect(
                url_for('home'))

        else:
            flash(f'Login Unsuccessful. Please check email and password{confirmed}', 'danger')

    return render_template('login.html', form=form)


@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:

            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file

        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()

        flash('Your account has been updated!', 'success')

        return redirect(url_for('account'))

    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email

    image_file = url_for('static', filename='img/' + current_user.image_file)

    return render_template('account.html', image_file=image_file, form=form)
    

@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(
            title=form.title.data,
            content=form.content.data,
            author=current_user)

        db.session.add(post)
        db.session.commit()

        flash('Your post has been created', 'success')

        return redirect(url_for('news'))

    return render_template('new_post.html',
                           form=form, legend='New Post')


@app.route('/news/<int:post_id>')
def post(post_id):
    '''
    Make a query for the post id
    If not found make a 404 message
    '''
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)


@app.route('/news/<int:post_id>/update', methods=['GET', 'POST'])
@login_required
def update_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)

    form = PostForm()
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data

        db.session.add(post)
        db.session.commit()

        flash('Your post has been updated!', 'success')

        return redirect(url_for('post', post_id=post.id))

    elif request.method == 'GET':
        form.title.data = post.title
        form.content.data = post.content

    return render_template('new_post.html',
                           form=form, legend='Update Post')


@app.route('/news/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)

    if post.author != current_user:
        abort(403)

    db.session.delete(post)
    db.session.commit()

    flash('Your post has been deleted!', 'success')

    return redirect(url_for('home'))


@app.route("/user/<string:username>")
def user_posts(username):
    '''
    Grabs all posts from the user
    Maybe in the future have it look to their account page
    '''
    page = request.args.get('page', 1, type=int)
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(
        author=user).order_by(
        Post.date_posted.desc()).paginate(
            page=page,
        per_page=5)

    return render_template('user_posts.html', posts=posts, user=user)


@app.route('/reset_password', methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        token = user.get_reset_token()
        reset_url = url_for('reset_token', token=token, _external=True)
        subject = 'Password Reset Request'
        html = render_template('reset_email.html', url=reset_url)
        send_email(user.email, subject, html)

        flash(
            'An email has been sent with instructions to reset your password',
            'info')

        return redirect(url_for('login'))

    return render_template('reset_request.html', form=form)


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('reset_request'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(
            sha256(
                (form.password.data +
                 user.email +
                 app.config['SECURITY_PASSWORD_SALT']).encode()).hexdigest()).decode('utf-8')
        user.password = hashed_password

        db.session.commit()

        flash(f'Your password has been updated!', 'success')

        return redirect(url_for('login'))
        
    return render_template('reset_token.html', form=form)


'''
Error Paths
'''


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html')