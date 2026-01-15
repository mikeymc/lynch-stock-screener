// ABOUTME: Renders AI-generated narrative with embedded chart placeholders
// ABOUTME: Parses {{CHART:chart_name}} tokens and injects corresponding React chart components

import { useMemo, useCallback, useState } from 'react'
import { Line } from 'react-chartjs-2'
import ReactMarkdown from 'react-markdown'
import { Card, CardContent } from '@/components/ui/card'

// Plugin to draw a dashed zero line
const zeroLinePlugin = {
    id: 'zeroLine',
    beforeDraw: (chart) => {
        const ctx = chart.ctx;
        const yAxis = chart.scales.y;
        const xAxis = chart.scales.x;

        if (yAxis && yAxis.min <= 0 && yAxis.max >= 0) {
            const y = yAxis.getPixelForValue(0);

            ctx.save();
            ctx.beginPath();
            ctx.moveTo(xAxis.left, y);
            ctx.lineTo(xAxis.right, y);
            ctx.lineWidth = 2;
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
            ctx.setLineDash([6, 4]);
            ctx.stroke();
            ctx.restore();
        }
    }
};

// Plugin to draw synchronized crosshair
const crosshairPlugin = {
    id: 'crosshair',
    afterDraw: (chart) => {
        const index = chart.config.options.plugins.crosshair?.activeIndex;

        if (index === null || index === undefined || index === -1) return;

        const ctx = chart.ctx;
        const yAxis = chart.scales.y;

        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data) return;

        const point = meta.data[index];

        if (point) {
            const x = point.x;

            ctx.save();
            ctx.beginPath();
            ctx.moveTo(x, yAxis.top);
            ctx.lineTo(x, yAxis.bottom);
            ctx.lineWidth = 1;
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
            ctx.setLineDash([5, 5]);
            ctx.stroke();
            ctx.restore();
        }
    }
};

// Stateless year tick callback for weekly data charts
const yearTickCallback = function (value, index, values) {
    const label = this.getLabelForValue(value)
    if (!label) return label

    const year = String(label).substring(0, 4)

    if (index === 0) return year

    const prevValue = values[index - 1].value
    const prevLabel = this.getLabelForValue(prevValue)
    const prevYear = prevLabel ? prevLabel.substring(0, 4) : null

    if (year !== prevYear) {
        return year
    }
    return null
};

// Custom Legend Component
const CustomLegend = ({ items }) => {
    if (!items || items.length === 0) return null

    return (
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2 mt-4 px-2">
            {items.map((item, idx) => (
                <div key={idx} className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                    <span
                        className="block"
                        style={{
                            width: 16,
                            height: 3,
                            backgroundColor: item.color,
                            borderRadius: 2,
                            ...(item.dashed ? { backgroundImage: `repeating-linear-gradient(90deg, ${item.color}, ${item.color} 4px, transparent 4px, transparent 8px)`, backgroundColor: 'transparent' } : {})
                        }}
                    />
                    <span>{item.label}</span>
                </div>
            ))}
        </div>
    )
}

export default function ChartNarrativeRenderer({ narrative, historyData }) {
    const [activeIndex, setActiveIndex] = useState(null)

    const handleHover = useCallback((event, elements) => {
        if (elements && elements.length > 0) {
            const index = elements[0].index;
            setActiveIndex(index);
        }
    }, []);

    const handleMouseLeave = useCallback(() => {
        setActiveIndex(null);
    }, []);

    const labels = historyData?.labels || historyData?.years || []

    // Calculate extended labels for estimate charts
    const getYearFromLabel = (label) => {
        if (!label) return null
        const match = String(label).match(/^(\d{4})/)
        return match ? parseInt(match[1]) : null
    }

    const lastHistoricalYear = labels.length > 0
        ? Math.max(...labels.map(getYearFromLabel).filter(y => y !== null))
        : new Date().getFullYear() - 1

    const hasEstimates = historyData?.analyst_estimates?.next_year

    const getExtendedLabels = () => {
        if (!hasEstimates) return labels
        return [...labels, String(lastHistoricalYear + 1)]
    }

    // Build estimate data for projection charts
    const buildEstimateData = (historicalData, metricKey, scaleFactor = 1) => {
        if (!hasEstimates) return null

        const nextYearEstimate = historyData.analyst_estimates.next_year
        if (!nextYearEstimate || Object.keys(nextYearEstimate).length === 0) return null

        const estimateData = new Array(labels.length + 1).fill(null)
        const estimateYearIdx = labels.length

        if (metricKey === 'revenue' && nextYearEstimate.revenue) {
            const estValue = nextYearEstimate.revenue.mean
            if (estValue != null) {
                estimateData[estimateYearIdx] = estValue / scaleFactor
                if (historicalData.length > 0 && estimateYearIdx > 0) {
                    const lastHistorical = historicalData[historicalData.length - 1]
                    if (lastHistorical != null) {
                        estimateData[estimateYearIdx - 1] = lastHistorical / scaleFactor
                    }
                }
            }
        } else if (metricKey === 'eps' && nextYearEstimate.eps) {
            const estValue = nextYearEstimate.eps.mean
            if (estValue != null) {
                estimateData[estimateYearIdx] = estValue / scaleFactor
                if (historicalData.length > 0 && estimateYearIdx > 0) {
                    const lastHistorical = historicalData[historicalData.length - 1]
                    if (lastHistorical != null) {
                        estimateData[estimateYearIdx - 1] = lastHistorical / scaleFactor
                    }
                }
            }
        }

        return estimateData
    }

    // Base chart options factory
    const createChartOptions = useCallback((title, yAxisLabel) => ({
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
            mode: 'index',
            intersect: false,
        },
        onHover: handleHover,
        plugins: {
            title: {
                display: true,
                text: title,
                font: { size: 14, weight: '600' },
                color: '#999999'
            },
            legend: {
                display: false
            },
            crosshair: {
                activeIndex: activeIndex
            }
        },
        scales: {
            x: {
                ticks: {
                    autoSkip: false,
                    maxRotation: 45,
                    minRotation: 45,
                    color: '#64748b'
                },
                grid: {
                    color: 'rgba(100, 116, 139, 0.1)'
                }
            },
            y: {
                title: {
                    display: true,
                    text: yAxisLabel,
                    color: '#64748b'
                },
                ticks: {
                    color: '#64748b'
                },
                grid: {
                    color: (context) => {
                        if (Math.abs(context.tick.value) < 0.00001) {
                            return 'transparent';
                        }
                        return 'rgba(100, 116, 139, 0.1)';
                    }
                }
            }
        }
    }), [activeIndex, handleHover])

    // Chart registry - maps placeholder names to chart configurations
    const chartRegistry = useMemo(() => ({
        revenue: () => (
            <div>
                <div className="h-64">
                    <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                        data={{
                            labels: getExtendedLabels(),
                            datasets: [
                                {
                                    label: 'Revenue (Billions)',
                                    data: historyData.revenue.map(r => r / 1e9),
                                    borderColor: 'rgb(75, 192, 192)',
                                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                                    pointRadius: activeIndex !== null ? 3 : 0,
                                    pointHoverRadius: 5
                                },
                                ...(hasEstimates ? [{
                                    label: 'Analyst Est.',
                                    data: buildEstimateData(historyData.revenue, 'revenue', 1e9),
                                    borderColor: 'rgba(20, 184, 166, 0.8)',
                                    backgroundColor: 'transparent',
                                    borderDash: [5, 5],
                                    pointRadius: 4,
                                    pointStyle: 'triangle',
                                    pointHoverRadius: 6,
                                    spanGaps: true,
                                }] : [])
                            ]
                        }}
                        options={{
                            ...createChartOptions('Revenue', 'Billions ($)'),
                            plugins: {
                                ...createChartOptions('Revenue', 'Billions ($)').plugins,
                                legend: { display: false }
                            }
                        }}
                    />
                </div>
                <CustomLegend items={[
                    { label: 'Revenue', color: 'rgb(75, 192, 192)' },
                    ...(hasEstimates ? [{ label: 'Analyst Est.', color: 'rgba(20, 184, 166, 0.8)', dashed: true }] : [])
                ]} />
            </div>
        ),

        net_income: () => (
            <div className="h-64">
                <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                    data={{
                        labels: labels,
                        datasets: [
                            {
                                label: 'Net Income (Billions)',
                                data: historyData.net_income?.map(ni => ni ? ni / 1e9 : null) || [],
                                borderColor: 'rgb(153, 102, 255)',
                                backgroundColor: 'rgba(153, 102, 255, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                            }
                        ]
                    }}
                    options={createChartOptions('Net Income', 'Billions ($)')}
                />
            </div>
        ),

        eps: () => (
            <div>
                <div className="h-64">
                    <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                        data={{
                            labels: getExtendedLabels(),
                            datasets: [
                                {
                                    label: 'EPS ($)',
                                    data: historyData.eps || [],
                                    borderColor: 'rgb(6, 182, 212)',
                                    backgroundColor: 'rgba(6, 182, 212, 0.2)',
                                    pointRadius: activeIndex !== null ? 3 : 0,
                                    pointHoverRadius: 5
                                },
                                ...(hasEstimates ? [{
                                    label: 'Analyst Est.',
                                    data: buildEstimateData(historyData.eps || [], 'eps', 1),
                                    borderColor: 'rgba(20, 184, 166, 0.8)',
                                    backgroundColor: 'transparent',
                                    borderDash: [5, 5],
                                    pointRadius: 4,
                                    pointStyle: 'triangle',
                                    pointHoverRadius: 6,
                                    spanGaps: true,
                                }] : [])
                            ]
                        }}
                        options={{
                            ...createChartOptions('Earnings Per Share', 'EPS ($)'),
                            plugins: {
                                ...createChartOptions('Earnings Per Share', 'EPS ($)').plugins,
                                legend: { display: false }
                            }
                        }}
                    />
                </div>
                <CustomLegend items={[
                    { label: 'EPS', color: 'rgb(6, 182, 212)' },
                    ...(hasEstimates ? [{ label: 'Analyst Est.', color: 'rgba(20, 184, 166, 0.8)', dashed: true }] : [])
                ]} />
            </div>
        ),

        dividend_yield: () => (
            <div className="h-64">
                <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                    data={{
                        labels: historyData.weekly_dividend_yields?.dates || [],
                        datasets: [
                            {
                                label: 'Dividend Yield (%)',
                                data: historyData.weekly_dividend_yields?.values || [],
                                borderColor: 'rgb(255, 205, 86)',
                                backgroundColor: 'rgba(255, 205, 86, 0.2)',
                                pointRadius: 0,
                                pointHoverRadius: 3,
                                borderWidth: 1.5,
                                tension: 0.1
                            }
                        ]
                    }}
                    options={{
                        ...createChartOptions('Dividend Yield', 'Yield (%)'),
                        scales: {
                            ...createChartOptions('Dividend Yield', 'Yield (%)').scales,
                            x: {
                                type: 'category',
                                ticks: {
                                    callback: yearTickCallback,
                                    maxRotation: 45,
                                    minRotation: 45,
                                    autoSkip: false
                                }
                            }
                        }
                    }}
                />
            </div>
        ),

        operating_cash_flow: () => (
            <div className="h-64">
                <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                    data={{
                        labels: labels,
                        datasets: [
                            {
                                label: 'Operating Cash Flow (Billions)',
                                data: historyData.operating_cash_flow?.map(ocf => ocf ? ocf / 1e9 : null) || [],
                                borderColor: 'rgb(54, 162, 235)',
                                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                            },
                        ],
                    }}
                    options={createChartOptions('Operating Cash Flow', 'Billions ($)')}
                />
            </div>
        ),

        free_cash_flow: () => (
            <div className="h-64">
                <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                    data={{
                        labels: labels,
                        datasets: [
                            {
                                label: 'Free Cash Flow (Billions)',
                                data: historyData.free_cash_flow?.map(fcf => fcf ? fcf / 1e9 : null) || [],
                                borderColor: 'rgb(34, 197, 94)',
                                backgroundColor: 'rgba(34, 197, 94, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                            },
                        ],
                    }}
                    options={createChartOptions('Free Cash Flow', 'Billions ($)')}
                />
            </div>
        ),

        capex: () => (
            <div className="h-64">
                <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                    data={{
                        labels: labels,
                        datasets: [
                            {
                                label: 'Capital Expenditures (Billions)',
                                data: historyData.capital_expenditures?.map(capex => capex ? Math.abs(capex) / 1e9 : null) || [],
                                borderColor: 'rgb(239, 68, 68)',
                                backgroundColor: 'rgba(239, 68, 68, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                            },
                        ],
                    }}
                    options={createChartOptions('Capital Expenditures', 'Billions ($)')}
                />
            </div>
        ),

        debt_to_equity: () => (
            <div className="h-64">
                <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                    data={{
                        labels: labels,
                        datasets: [
                            {
                                label: 'Debt-to-Equity Ratio',
                                data: historyData.debt_to_equity,
                                borderColor: 'rgb(255, 99, 132)',
                                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                                pointRadius: activeIndex !== null ? 3 : 0,
                                pointHoverRadius: 5
                            }
                        ]
                    }}
                    options={createChartOptions('Debt-to-Equity', 'D/E Ratio')}
                />
            </div>
        ),

        stock_price: () => (
            <div>
                <div className="h-64">
                    <Line plugins={[zeroLinePlugin, crosshairPlugin]}
                        data={{
                            labels: historyData.weekly_prices?.dates?.length > 0
                                ? historyData.weekly_prices.dates
                                : labels,
                            datasets: [
                                {
                                    label: 'Stock Price ($)',
                                    data: historyData.weekly_prices?.prices?.length > 0
                                        ? historyData.weekly_prices.prices
                                        : historyData.price,
                                    borderColor: 'rgb(255, 159, 64)',
                                    backgroundColor: 'rgba(255, 159, 64, 0.2)',
                                    pointRadius: 0,
                                    pointHoverRadius: 3,
                                    borderWidth: 1.5,
                                    tension: 0.1
                                },
                                // Price target band and mean line if available
                                ...(historyData.price_targets ? [
                                    {
                                        label: 'Target High',
                                        data: (historyData.weekly_prices?.dates || labels).map(() => historyData.price_targets.high),
                                        borderColor: 'transparent',
                                        backgroundColor: 'rgba(34, 197, 94, 0.15)',
                                        fill: '+1',
                                        pointRadius: 0,
                                    },
                                    {
                                        label: 'Target Low',
                                        data: (historyData.weekly_prices?.dates || labels).map(() => historyData.price_targets.low),
                                        borderColor: 'transparent',
                                        backgroundColor: 'rgba(34, 197, 94, 0.15)',
                                        fill: false,
                                        pointRadius: 0,
                                    },
                                    {
                                        label: 'Target Mean',
                                        data: (historyData.weekly_prices?.dates || labels).map(() => historyData.price_targets.mean),
                                        borderColor: 'rgba(34, 197, 94, 0.8)',
                                        backgroundColor: 'transparent',
                                        borderDash: [5, 5],
                                        pointRadius: 0,
                                        borderWidth: 2,
                                    },
                                ] : [])
                            ]
                        }}
                        options={{
                            ...createChartOptions('Stock Price', 'Price ($)'),
                            scales: {
                                ...createChartOptions('Stock Price', 'Price ($)').scales,
                                x: {
                                    type: 'category',
                                    ticks: {
                                        callback: yearTickCallback,
                                        maxRotation: 45,
                                        minRotation: 45,
                                        autoSkip: false
                                    }
                                }
                            }
                        }}
                    />
                </div>
                <CustomLegend items={[
                    { label: 'Stock Price', color: 'rgb(255, 159, 64)' },
                    ...(historyData.price_targets ? [
                        { label: 'Analyst Target Range', color: 'rgba(34, 197, 94, 0.5)' },
                        { label: 'Target Mean', color: 'rgba(34, 197, 94, 0.8)', dashed: true }
                    ] : [])
                ]} />
            </div>
        ),

        pe_ratio: () => {
            const weeklyPE = historyData?.weekly_pe_ratios
            const useWeeklyPE = weeklyPE?.dates?.length > 0 && weeklyPE?.values?.length > 0
            const peLabels = useWeeklyPE ? weeklyPE.dates : (historyData?.labels || labels)
            const peData = useWeeklyPE ? weeklyPE.values : (historyData?.pe_ratio || historyData?.pe_history || [])

            return (
                <div className="h-64">
                    <Line
                        key={useWeeklyPE ? 'weekly' : 'annual'}
                        plugins={[zeroLinePlugin, crosshairPlugin]}
                        data={{
                            labels: peLabels,
                            datasets: [
                                {
                                    label: 'P/E Ratio',
                                    data: peData,
                                    borderColor: 'rgb(168, 85, 247)',
                                    backgroundColor: 'rgba(168, 85, 247, 0.2)',
                                    pointRadius: 0,
                                    pointHoverRadius: 3,
                                    borderWidth: 1.5,
                                    tension: 0.1,
                                    spanGaps: true
                                }
                            ]
                        }}
                        options={{
                            ...createChartOptions('P/E Ratio', 'P/E'),
                            scales: {
                                ...createChartOptions('P/E Ratio', 'P/E').scales,
                                x: {
                                    type: 'category',
                                    ticks: {
                                        callback: yearTickCallback,
                                        maxRotation: 45,
                                        minRotation: 45,
                                        autoSkip: true,
                                        maxTicksLimit: 20
                                    }
                                }
                            }
                        }}
                    />
                </div>
            )
        },
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }), [historyData, activeIndex, labels, hasEstimates, createChartOptions])

    // Parse the narrative into thematic sections
    const sections = useMemo(() => {
        if (!narrative) return []

        // Split by ### headers
        const sectionParts = narrative.split(/(?=###\s+)/g)
        const parsedSections = []

        sectionParts.forEach((part, index) => {
            const lines = part.trim().split('\n')
            let title = ''
            let content = part

            if (lines[0].startsWith('### ')) {
                title = lines[0].replace('### ', '').trim()
                content = lines.slice(1).join('\n').trim()
            } else if (index === 0) {
                title = 'Introduction'
            }

            if (content) {
                // Parse the content of this section for text and charts
                const chartPattern = /\{\{CHART:(\w+)\}\}/g
                const elements = []
                let lastIndex = 0
                let match

                while ((match = chartPattern.exec(content)) !== null) {
                    // Add text before this chart
                    if (match.index > lastIndex) {
                        const textBefore = content.slice(lastIndex, match.index).trim()
                        if (textBefore) {
                            elements.push({ type: 'text', content: textBefore })
                        }
                    }

                    // Add the chart
                    const chartName = match[1]
                    if (chartRegistry[chartName]) {
                        elements.push({ type: 'chart', name: chartName })
                    } else {
                        elements.push({ type: 'text', content: `[Unknown chart: ${chartName}]` })
                    }

                    lastIndex = match.index + match[0].length
                }

                // Add remaining text
                if (lastIndex < content.length) {
                    const remainingText = content.slice(lastIndex).trim()
                    if (remainingText) {
                        elements.push({ type: 'text', content: remainingText })
                    }
                }

                parsedSections.push({ title, elements })
            }
        })

        return parsedSections
    }, [narrative, chartRegistry])

    if (!narrative) {
        return null
    }

    return (
        <div className="chart-narrative-container flex flex-col gap-8 pb-12" onMouseLeave={handleMouseLeave}>
            {sections.map((section, sIdx) => (
                <Card
                    key={sIdx}
                    className="overflow-hidden border-border bg-card shadow-md transition-all duration-300 hover:shadow-lg"
                >
                    <div className="px-6 py-4 border-b border-border bg-muted/30">
                        <h3 className="text-lg font-bold" style={{ color: '#999999' }}>
                            {section.title}
                        </h3>
                    </div>
                    <CardContent className="p-6 flex flex-col gap-6">
                        {section.elements.map((item, eIdx) => (
                            <div key={eIdx}>
                                {item.type === 'text' ? (
                                    <div className="prose prose-sm max-w-none prose-p:mb-4 prose-p:leading-relaxed prose-headings:text-foreground prose-strong:text-foreground prose-p:text-foreground/90 [&>p]:mb-4 [&>p]:leading-relaxed">
                                        <ReactMarkdown>{item.content}</ReactMarkdown>
                                    </div>
                                ) : (
                                    <div className="chart-wrapper chart-container bg-background rounded-xl p-4 border border-border shadow-inner">
                                        {chartRegistry[item.name]?.()}
                                    </div>
                                )}
                            </div>
                        ))}
                    </CardContent>
                </Card>
            ))}
        </div>
    );
}
