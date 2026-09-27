# Plataforma PIAs

## Requisitos

Guía completa de instalación: <enlace a este documento>

## Arranque

1. git clone git@github.com:pias-rag-universidad-caldas/pias-plataforma.git
2. cd pias-plataforma
3. pnpm env:init (copia cada apps/*/.env.example a .env)
4. pnpm install
5. pnpm infra:up
6. pnpm modelos (o: pnpm modelos medio)
7. pnpm seed
8. pnpm dev

## URLs

- Admin: http://localhost:3000
- Público: http://localhost:4321
- API: http://localhost:3001
- IA: http://localhost:8001/docs
- Neo4j: http://localhost:7474
- Keycloak: http://localhost:8080

## Usuarios de prueba

profe / profe123 · facultad / facultad123 · consejo / consejo123 · admin / admin123
