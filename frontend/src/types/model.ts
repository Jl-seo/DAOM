import { FIELD_TYPES, DATA_STRUCTURES } from '../constants'

export type FieldType = typeof FIELD_TYPES[number]['value']
export type DataStructureType = typeof DATA_STRUCTURES[number]['id']

export interface Field {
    key: string
    label: string
    description: string
    rules: string
    type: FieldType
}

export interface Model {
    id: string
    name: string
    description: string
    global_rules: string
    data_structure: DataStructureType
    model_type?: 'extraction' | 'comparison'
    fields: Field[]
}
