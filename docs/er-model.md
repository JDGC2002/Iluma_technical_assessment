# My relational model

I use this model to separate the main entities and their relationships. The table definitions and constraints are in [schema.sql](../sql/schema.sql). My reasons for the model are in the [decision log](decisions.md).

```mermaid
erDiagram
    direction TB

    companies |o..o{ jobs : identifies
    job_titles ||..o{ jobs : describes
    platforms |o..o{ jobs : publishes
    countries |o..o{ locations : groups
    locations |o..o{ jobs : locates
    jobs ||--o{ job_skills : lists
    skills ||--o{ job_skills : appears_in
    skills ||--o{ skill_category_memberships : has
    skill_categories ||--o{ skill_category_memberships : groups
    jobs ||--o{ job_schedules : offers
    schedule_types ||--o{ job_schedules : describes

    companies {
        bigint company_id PK
        text name
        text name_key UK
    }

    job_titles {
        bigint title_id PK
        text full_title UK
        text short_title
    }

    platforms {
        bigint platform_id PK
        text name
        text name_key UK
    }

    countries {
        bigint country_id PK
        text name UK
    }

    locations {
        bigint location_id PK
        text label
        bigint country_id FK
    }

    jobs {
        bigint job_id PK
        bytea record_hash UK
        bigint company_id FK
        bigint title_id FK
        bigint platform_id FK
        bigint location_id FK
        text search_location
        timestamp job_posted_date
        boolean job_work_from_home
        boolean job_no_degree_mention
        boolean job_health_insurance
        text salary_rate
        numeric salary_year_avg
        numeric salary_hour_avg
        boolean skills_reported
        boolean skill_categories_reported
    }

    skills {
        bigint skill_id PK
        text name UK
    }

    job_skills {
        bigint job_id PK, FK
        bigint skill_id PK, FK
    }

    skill_categories {
        bigint category_id PK
        text name UK
    }

    skill_category_memberships {
        bigint skill_id PK, FK
        bigint category_id PK, FK
    }

    schedule_types {
        bigint schedule_type_id PK
        text name UK
    }

    job_schedules {
        bigint job_id PK, FK
        bigint schedule_type_id PK, FK
    }
```
