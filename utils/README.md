### **Install `pyenv`**  

`pyenv` is a flexible tool that makes it easy to manage multiple Python versions, including switching between them on a per-project basis.

First, install `pyenv` by running:

```bash
curl https://pyenv.run | bash
```

Add the following lines to your `.bashrc`, `.bash_profile`, or `.zshrc` file (depending on your shell):

```bash
export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
```

Then, reload your shell:

```bash
source ~/.bashrc  
```

Now, you can install multiple Python versions:

```bash
pyenv install 3.6.9
pyenv install 3.8.10
```

Set a global default version (applies system-wide):

```bash
pyenv global 3.8.10
```
Set a local version for a specific project (applies only in the current directory):

```bash
pyenv local 3.6.9
```
Verify the Python Version
To check which Python version is currently being used, run:

```bash
pyenv versions
python3 -V
```

Easily switch between different installed Python versions:

```bash
pyenv global 3.8.10
pyenv global 3.6.9    # Switch back to Python 3.6.9
```