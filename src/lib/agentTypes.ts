import {
  BarChartIcon,
  GearIcon,
  HeadsetIcon,
  HierarchyIcon,
  MegaphoneIcon,
  PencilIcon,
  SearchIcon,
  type IconComponent,
} from '../components/icons'
import type { Database } from './database.types'

export type AgentType = Database['public']['Enums']['agent_type']

export const AGENT_TYPES: {
  value: AgentType
  label: string
  description: string
  icon: IconComponent
}[] = [
  {
    value: 'general',
    label: 'Manager',
    description: 'Answers questions and plans with you, and hands tasks to the right agent.',
    icon: HierarchyIcon,
  },
  {
    value: 'lead_research',
    label: 'Lead Research',
    description: 'Find and qualify real companies as sales leads.',
    icon: SearchIcon,
  },
  {
    value: 'sales_outreach',
    label: 'Sales & Outreach',
    description: 'Contact and follow up with your qualified leads via email.',
    icon: MegaphoneIcon,
  },
  {
    value: 'content_copy',
    label: 'Content & Copy',
    description: 'Blog posts, ad copy, and social captions.',
    icon: PencilIcon,
  },
  {
    value: 'customer_support',
    label: 'Customer Support',
    description: 'Triage tickets and draft replies you approve.',
    icon: HeadsetIcon,
  },
  {
    value: 'data_reporting',
    label: 'Data & Reporting',
    description: 'Clean weekly reports from raw numbers.',
    icon: BarChartIcon,
  },
  {
    value: 'operations',
    label: 'Operations',
    description: 'Runs your other agents on a schedule: reports, follow-ups, research and posts.',
    icon: GearIcon,
  },
]

export const AGENT_LABELS = Object.fromEntries(
  AGENT_TYPES.map((a) => [a.value, a.label]),
) as Record<AgentType, string>
