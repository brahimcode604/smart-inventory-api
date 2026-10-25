# Smart Inventory API

API REST de gestion de produits, catégories, clients et commandes avec FastAPI,
SQLAlchemy 2 et PostgreSQL.

## Structure

```text
app/
  core/          Configuration et sécurité (JWT, hachage)
  db/            Base SQLAlchemy et sessions PostgreSQL
  routers/       Routes auth, catégories, produits, clients et commandes
  dependencies.py
  models.py      Schéma SQLAlchemy
  schemas.py     Validation et contrats de l'API (Pydantic)
  main.py
.env.example
docker-compose.yml
requirements.txt
```

## Démarrage local

1. Créer et activer un environnement virtuel Python 3.10 ou plus récent :

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Créer la configuration locale et générer une clé JWT aléatoire (ne jamais
   utiliser la clé d'exemple en production) :

   ```powershell
   Copy-Item .env.example .env
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   Copier la valeur générée dans `JWT_SECRET_KEY` de `.env`.

3. Démarrer PostgreSQL avec Docker Compose :

   ```powershell
   docker compose up -d db
   ```

4. Démarrer l'API :

   ```powershell
   uvicorn app.main:app --reload
   ```

   Documentation interactive : <http://127.0.0.1:8000/docs>.

Au démarrage, les tables SQLAlchemy sont créées si elles n'existent pas.
Pour un déploiement en production, gérer les évolutions de schéma avec Alembic
plutôt que `create_all`.

## Schéma des données

Le schéma est défini dans `app/models.py` :

- `users` : comptes et mots de passe hachés.
- `categories` : catégories uniques; la suppression d'une catégorie met
  `products.category_id` à `NULL`.
- `products` : SKU unique, prix décimal, stock entier non négatif et catégorie
  optionnelle.
- `customers` : coordonnées client, e-mail unique.
- `orders` : client, date UTC et total calculé.
- `order_items` : produit, quantité et prix unitaire figé au moment de la vente.

Les contraintes SQL interdisent les prix négatifs et les quantités nulles ou
négatives. Une commande référence son client et ses produits; une commande
existante empêche la suppression de ses références.

## Authentification

Créer un compte avec `POST /api/v1/auth/register`, puis récupérer un JWT via
`POST /api/v1/auth/login` en envoyant un formulaire OAuth2 (`username` = e-mail,
`password` = mot de passe). Transmettre ensuite le jeton dans l'en-tête :

```text
Authorization: Bearer <access_token>
```

Les routes CRUD et commandes requièrent un jeton. L'inscription est ouverte
dans cette base de départ; en production, la restreindre ou ajouter un
processus d'invitation/gestion des rôles selon le besoin métier.

## Routes principales

Toutes les routes métier sont préfixées par `/api/v1`.

| Méthode | Route | Accès | Description |
|---|---|---|---|
| POST | `/auth/register` | Public | Créer un compte |
| POST | `/auth/login` | Public | Obtenir un JWT |
| GET, POST | `/categories` | JWT | Lister/créer |
| GET, PATCH, DELETE | `/categories/{id}` | JWT | Lire/modifier/supprimer |
| GET, POST | `/products` | JWT | Lister/créer |
| GET, PATCH, DELETE | `/products/{id}` | JWT | Lire/modifier/supprimer |
| GET, POST | `/customers` | JWT | Lister/créer |
| GET, PATCH, DELETE | `/customers/{id}` | JWT | Lire/modifier/supprimer |
| GET, POST | `/orders` | JWT | Lister/créer |
| GET | `/orders/{id}` | JWT | Lire une commande |

## Création d'une commande

`POST /api/v1/orders` reçoit un client et une liste de produits/quantités :

```json
{
  "customer_id": 1,
  "items": [
    { "product_id": 1, "quantity": 2 },
    { "product_id": 3, "quantity": 1 }
  ]
}
```

La création verrouille les lignes produits PostgreSQL, agrège les quantités
d'un même produit, vérifie le stock puis crée la commande, fige les prix et
décrémente les stocks dans la même transaction. Si un produit est absent ou
le stock insuffisant, la commande échoue sans décrément partiel.
