
```mermaid
flowchart TD
    %% Core Flow
    A[Customer searches product on Google Shopping] --> B[Google Merchant Center]
    B --> C[GMC checks shipping settings]

    C -->|Uses flat/advanced/carrier| D{Shipping Method?}
    
    D -->|Advanced Rate| E[GMC uses predefined region & rate mapping]
    D -->|Carrier Calculated| F[GMC expects real-time rates from merchant]

    F --> G[Merchant implements custom shipping integration]

    G --> H[Magento 2 Module - GoogleFreight]
    H --> I[Helper: FreightApi.php]
    I --> J[REST API → Azure Cosmos DB]
    J --> K[Returns deliveryPossible + deliveryRate]

    K --> L[Magento returns rate result]
    L --> M[OfferShippingDetails injected into page JSON-LD]

    M --> N[Googlebot scrapes structured data]

    E --> O[Google Shopping displays product + shipping rate]
    N --> O

    %% Subsystems
    subgraph Magento_2_Store
        H
        I
        L
        M
    end

    subgraph GMC_Shipping_Sync_Script_Python
        P[Periodic Sync Script]
        P --> Q[Query rates from Magento or Cosmos DB]
        Q --> R[Format as Google Shipping Settings Schema]
        R --> S[Push to GMC API via OAuth2]
        S --> T[GMC updates shipping rate rules]
        T --> C
    end

    %% Tokyo Midnight Styling
    style A fill:#1e1e2f,stroke:#00d4ff,color:#00d4ff
    style B fill:#1e1e2f,stroke:#00d4ff,color:#00d4ff
    style C fill:#2c2c3c,stroke:#80cbc4,color:#80cbc4
    style D fill:#2c2c3c,stroke:#4dd0e1,color:#4dd0e1
    style E fill:#2c2c3c,stroke:#00bcd4,color:#00bcd4
    style F fill:#2c2c3c,stroke:#00acc1,color:#00acc1
    style G fill:#212130,stroke:#ffca28,color:#ffca28
    style H fill:#212130,stroke:#ffdd57,color:#ffdd57
    style I fill:#212130,stroke:#ffc107,color:#ffc107
    style J fill:#212130,stroke:#ff9800,color:#ff9800
    style K fill:#212130,stroke:#ff7043,color:#ff7043
    style L fill:#212130,stroke:#81c784,color:#81c784
    style M fill:#1f2d20,stroke:#8bc34a,color:#8bc34a
    style N fill:#1e1e2f,stroke:#66bb6a,color:#66bb6a
    style O fill:#1e1e2f,stroke:#00e676,color:#00e676
    style P fill:#241f3a,stroke:#9575cd,color:#9575cd
    style Q fill:#241f3a,stroke:#7986cb,color:#7986cb
    style R fill:#241f3a,stroke:#5c6bc0,color:#5c6bc0
    style S fill:#241f3a,stroke:#3f51b5,color:#3f51b5
    style T fill:#241f3a,stroke:#1e88e5,color:#1e88e5

````
