-- Governed by nation-scorecard.odcs.yaml (ODCS id: nation-scorecard)
with revenue as (
    select
        nation_name,
        region_name,
        sum(net_revenue) as net_revenue,
        sum(order_count) as order_count,
        sum(customer_count) as customer_count
    from {{ source('tpch_revenue_by_region', 'revenue_by_region') }}
    group by nation_name, region_name
),

customers as (
    -- customers who ordered, consistent with customer_count
    select
        customer_nation as nation_name,
        avg(lifetime_net_revenue) as avg_customer_lifetime_value
    from {{ source('tpch_customer_lifetime_value', 'customer_lifetime_value') }}
    where total_orders > 0
    group by customer_nation
),

shipping as (
    -- re-weight the per-ship-mode rates by shipment count
    select
        customer_nation as nation_name,
        cast(sum(late_deliveries) as double) / nullif(sum(shipment_count), 0) as late_delivery_rate,
        cast(sum(returned_items) as double) / nullif(sum(shipment_count), 0) as return_rate
    from {{ source('tpch_shipping_analysis', 'shipping_analysis') }}
    group by customer_nation
),

suppliers as (
    select
        supplier_nation as nation_name,
        count(*) as local_suppliers,
        sum(net_revenue) as local_supplier_revenue
    from {{ source('tpch_supplier_performance', 'supplier_performance') }}
    group by supplier_nation
)

select
    cast(r.nation_name as varchar) as nation,
    cast(r.region_name as varchar) as region,
    cast(r.net_revenue as double) as net_revenue,
    cast(r.order_count as bigint) as order_count,
    cast(r.customer_count as bigint) as customer_count,
    cast(c.avg_customer_lifetime_value as double) as avg_customer_lifetime_value,
    cast(sh.late_delivery_rate as double) as late_delivery_rate,
    cast(sh.return_rate as double) as return_rate,
    cast(coalesce(su.local_suppliers, 0) as bigint) as local_suppliers,
    cast(coalesce(su.local_supplier_revenue, 0) as double) as local_supplier_revenue
from revenue r
left join customers c on r.nation_name = c.nation_name
left join shipping sh on r.nation_name = sh.nation_name
left join suppliers su on r.nation_name = su.nation_name
